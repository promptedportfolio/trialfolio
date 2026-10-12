# Trial Folio user guide

> **The [user manual](https://promptedportfolio.github.io/trialfolio/) now covers these workflows,** as tutorials, how-to guides, reference, and explanation. This guide stays until release 0.4.0's documentation task turns it into a page that points there. Until then, both are kept up to date.

This guide walks through Trial Folio's workflows, from setting up to reading a report: release 0.1.0's; the review 0.2.0 adds, which compares saved runs; and the experiment 0.3.0 adds, which runs a baseline screen and a few variants of it under one plan. Each workflow ends with what to check, so you can confirm it works as described.

It describes behavior; it doesn't define it. Where it and an owning document disagree, such as [contracts.md](contracts.md) or a release specification, [0.1.0's](releases/0.1.0-api-execution.md), [0.2.0's](releases/0.2.0-review.md), or [0.3.0's](releases/0.3.0-experiments.md), the owning document wins, and this guide is the one to fix.

**Platforms.** So far, Trial Folio has been tested on macOS only. The commands below are for macOS and Linux shells.

**Your license.** [LICENSE](../LICENSE) governs every copy of Trial Folio, including one you run from this repository. The README's [License section](../README.md#license) summarizes who may use it.

## 1. Set up

Until Trial Folio is released as a package, run it from a copy of this repository.

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
   - `.gitignore`, which keeps credential files, runs, reports, and reviews out of Git, if you keep the folder in a repository

   The folder must be new or empty. Given no folder, `trialfolio init` sets up the current one. It needs no license acknowledgment, and sends nothing.

**Check:**

- `trialfolio --version` prints the version of the tag your copy came from, such as `trialfolio 0.2.1` from `v0.2.1`. A copy of `main` prints the next release's version, `0.3.0`, which the package takes once that release's specification is complete ([D-26](spec.md#decisions)).
- `trialfolio --help` lists `init`, `run`, `report`, `demo`, `review`, and `license`.
- `trialfolio init ~/research` exits 0 without asking you to acknowledge the license. The folder holds exactly `screen.yaml`, `README.md`, and `.gitignore`, with no `logs/` folder.
- Running it again on the same folder fails with `output.not_empty`, exit code 4, and changes nothing.

## 2. Acknowledge the license

`run`, `report`, `demo`, and `review` need a one-time acknowledgment of the license and the research notice. `--version`, `--help`, `trialfolio init`, and `trialfolio license` don't.

1. Read them: `trialfolio license`. It prints the license, the full research notice, and whether you've acknowledged them.
2. Acknowledge them, in one of three ways:
   - **At the terminal.** The first time you run `run`, `report`, `demo`, or `review`, it shows the concise notice and asks you to type `accept`.
   - **Ahead of time.** `trialfolio license --accept`.
   - **For one command, recording nothing.** Set `TRIALFOLIO_ACCEPT_LICENSE=LicenseRef-NSPRL-1.1/1.0`, which suits scripts.

**Check:**

- Before you acknowledge, `trialfolio demo --out demo/` from a script, or with its input redirected, fails with `license.not_acknowledged`, exit code 2, and writes nothing.
- After `trialfolio license --accept`, the last line of `trialfolio license` says "Acknowledged", with the time and the file it's recorded in. The record holds only the license identifier, the notice version, the time, and how you acknowledged.
- Any value of `TRIALFOLIO_ACCEPT_LICENSE` but the exact one is rejected, even after you've acknowledged. An empty one counts as unset.
- A new version of the license asks again. Release 0.2.1 brings version 1.1, so an acknowledgment of version 1.0, from 0.1.0 or 0.2.0, doesn't cover it.

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

A screen configuration is a YAML file describing one long-only stock screen backtest. Start from your workspace's `screen.yaml`. It has the settings of this example, which Portfolio123 accepted in a live call, with a comment on each key, and its `purpose` line commented out:

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
- The same configuration, with the same versions of Trial Folio, `p123api`, `requests`, and `urllib3`, gives the same plan hash every time, in any output directory. Changing a setting, the title, or the purpose changes it, and so does upgrading any of them.

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

Trial Folio sends them only to Portfolio123's API, directly. It ignores proxy settings and `.netrc`, and if `SSLKEYLOGFILE` is set, `trialfolio run` warns and ignores it.

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

## 10. Compare runs with a review

`trialfolio review` compares saved runs with a baseline you choose. It shows which settings differ, as changes you declared or as unexplained mismatches, and how each metric moved. It reads runs that `trialfolio run` or `trialfolio demo` wrote, offline: it sends nothing, and needs no credentials. It doesn't rank the runs, or say which strategy is better.

1. Write a review configuration, a YAML file that names the runs and the baseline. Put it in your workspace, and name each run by its path from there:

   ```yaml
   kind: review
   schema_version: 1.0.0
   title: Holdings 25 versus 50
   purpose: Check whether doubling holdings changes risk as expected.   # optional
   baseline: hold25
   results:
     - label: hold25
       run: runs/hold25
     - label: hold50
       run: runs/hold50
       description: The same screen, with 50 holdings.                 # optional
       intended_changes:
         - setting: max_holdings
           reason: Doubling holdings is the change under review.
   ```

   - **Labels** name the results in the review, and `baseline` is one of them. A label is lowercase letters, digits, `-`, and `_`, starts with a letter or a digit, and is at most 64 characters long. It names a folder in the review, so it can't be a name Windows reserves, such as `con` or `nul`.
   - **A `run` path is read from the configuration's folder,** wherever you run the command from, unless it's absolute. Keep it relative, as above. The review keeps a byte-for-byte copy of its configuration, so an absolute path, such as `/Users/you/research/runs/hold25`, would show anyone you share the review with where you keep your runs.
   - **Declare each change you meant to make,** under the result that makes it, with a reason. A declared change is shown as intended. A difference you didn't declare is an unexplained mismatch, and it's flagged in a critical category: the dates, the benchmark, the currency, the costs, the execution, the universe, the data source, and the strategy. You can declare 12 settings: `universe`, `rules`, `ranking`, `max_holdings`, `benchmark`, `start_date`, `end_date`, `rebalance_weeks`, `transaction_price`, `slippage_percent`, `pit_method`, and `precision`. The baseline declares nothing.

   [The review configuration](contracts.md#review-configuration) gives every key's rules.

2. Review the runs, into a new or empty directory:

   ```sh
   trialfolio review review.yaml --out reviews/holdings/
   ```

To try it without credentials, write two demo runs, `trialfolio demo --out runs/demo-a/` and `trialfolio demo --out runs/demo-b/`, and review them with a configuration that names them.

A review's directory holds:

| Path | What it is |
|---|---|
| `report.html` | The review's report: one self-contained file, with no scripts, that opens offline |
| `normalized/differences.csv` | For each result but the baseline, its 23 settings and then its 20 metrics, each compared with the baseline's |
| `manifest.json` | Which run each label names, the comparison's method, its counts, and every file's hash. It's written last, so a review without one is incomplete. |
| `configuration.yaml` | Your review configuration, byte for byte |
| `inputs/<label>/` | Byte-for-byte copies of each run's `manifest.json`, `plan.json`, and normalized tables, so the review stands on its own |
| `logs/trialfolio.log` | The review's log |

It doesn't copy a run's request, its response, or its report.

**Keep reviews out of Git.** A review of real runs holds Portfolio123 data, in its copies of their tables, as a run does. The `.gitignore` that `trialfolio init` writes keeps `reviews/` out of Git, as it does `runs/` and `reports/`, so write reviews there. A workspace that Trial Folio 0.1.0 set up lacks that line: if you keep it in Git, add `/reviews/` to its `.gitignore`.

**In the report:**

- The research notice, the Portfolio123 data statement, and "Not assessed", as in a run's report.
- Each result's benchmark beside the baseline's.
- The intended changes, apart from the unexplained mismatches, and any other setting that's flagged, such as a date whose coverage differs.
- Each result's metrics beside the baseline's, with the difference only where the two are comparable. It's in percentage points (`pp`) for percent metrics, and never has more decimal places than the two values. A metric that depends on the benchmark isn't differenced when the benchmarks differ, and no metric but the coverage is when the periods differ. The report gives the reason.
- A missing value shows as unavailable, with the reason its run's `metrics.csv` gives, never as zero.
- A result whose run has no tables, because its request failed or its response was invalid, is still compared: its settings from its plan, and every metric as unavailable. The report says why it has no tables.
- A synthetic result, from `trialfolio demo`, is named before any result, and labeled synthetic wherever its values appear.
- It links only to the review's own files, never to the runs, and never shows a `run` path.

**Check:**

- It exits 0. stdout says "Review completed", where the report is, how many setting rows are flagged and how many metric rows are unavailable, the review ID, and that statistical validation and trading readiness are not assessed.
- In `differences.csv`, the `intended_change` rows are the changes you declared. A declared change whose values are the same is `same`, flagged `intended_change_not_observed`.
- When two results' runs saved byte-identical responses, as two demo runs do, it warns that they share one response, and the metric rows of each but the baseline are flagged `identical_source`.
- The runs' directories aren't changed.
- A `run` directory that doesn't exist fails with `input.not_found`, and one that isn't a complete run with `input.not_a_run`, both with exit code 3. The message names the result's label and its `run` path, and nothing is written.
- Reviewing into a directory that isn't empty fails with `output.not_empty`, exit code 4, and changes nothing in it.

## 11. Run an experiment

An experiment runs a baseline screen and a few variants of it, each changing one setting of the baseline, under one plan, one approval, and one budget. Trial Folio compiles every case before it sends anything, runs the cases one at a time, and records every attempt, including those that fail. It doesn't rank the cases, or say which is better.

Each case is a screen backtest, sent just as a screen configuration with its settings would be, so each costs 5 API credits.

1. Write an experiment configuration, a YAML file. This is the documented example, each of whose cases Portfolio123 accepted in a live call:

   ```yaml
   kind: experiment
   schema_version: 1.0.0
   experiment_id: earnyield-sensitivity                 # names the experiment; never sent
   title: Earnings yield sensitivity
   purpose: How do holdings, slippage, and a stricter liquidity rule change the earnings-yield screen's results?
   prior_research:
     status: partial                                    # complete, partial, or unknown
     description: Earlier backtests of this screen in the Portfolio123 website compared 25 and 50 holdings. Other variations tried there weren't recorded.
   baseline:
     universe: 'SP500'
     rules:
       - 'AvgDailyTot(30) > 1000000'
     ranking:
       formula: 'EarnYield'
       lower_is_better: false
     max_holdings: 25
     benchmark: 'SPY'
     start_date: 2016-01-01
     end_date: 2025-12-31
     rebalance_weeks: 4
     transaction_price: open
     slippage_percent: 0.25
     pit_method: complete
     precision: 4
   variants:
     rules:
       - key: liquidity-100m
         description: A stricter liquidity floor, 100 million dollars a day.   # optional
         replace: 'AvgDailyTot(30) > 1000000'
         with: 'AvgDailyTot(30) > 100000000'
     max_holdings:
       - key: holdings-50
         value: 50
     slippage_percent:
       - key: slippage-050
         value: 0.5
   budget:
     provider_requests: 6
   ```

   - **The research context.** `experiment_id` names the experiment, as a review's labels name results: lowercase letters, digits, `-`, and `_`. `purpose`, the question the experiment addresses, is required. `prior_research` declares the earlier work on the same idea whose results you saw, in Trial Folio or anywhere else: `complete` when its description accounts for all of it, or says there was none; `partial` when there was more than it describes; or `unknown`. A description is required with `complete` or `partial`. Trial Folio records the declaration as you wrote it, and can't verify it. None of these is sent.
   - **The baseline** holds a screen's settings: the keys of a [screen configuration](#4-write-a-screen-configuration) from `universe` to `data_vendor`, with the same rules, so the text Portfolio123 receives goes in quotes. It has no `kind`, `schema_version`, `title`, or `purpose`: those are the experiment's. Every case uses the baseline's universe, ranking, benchmark, and dates.
   - **Each variant changes one setting** of the baseline, and is listed under that setting, with a `key` that names its case, and an optional `description`. Four settings can vary, those live calls verified:
     - `rules`: `replace` one of the baseline's rules, written exactly as it is there, `with` another, as for a stricter liquidity floor; or `add` a rule, such as `'MktCap > 300'`, which excludes microcaps.
     - `max_holdings`, `rebalance_weeks` (1 or 4), and `slippage_percent`: a `value` other than the baseline's.

     A variant of any other setting, such as `universe`, fails with `config.invalid`. Another universe, or another `experiment_id`, is another experiment.
   - **The default variant.** Without a `rebalance_weeks` list, Trial Folio adds a case for the other verified rebalance frequency: `rebalance-weeks-1` here, since the baseline rebalances every 4 weeks. It costs 5 credits, like any case. `rebalance_weeks: []` turns it off.
   - **The budget** is the most provider requests the experiment may send, across every run of it, repeats included. It must be at least the number of cases, so each can be sent once. One more, as here, leaves room for one [repeat](#12-resume-repeat-or-revise-an-experiment). The plan shows its credits, at 5 a request.
   - **The cases run in this order:** the baseline, then the variants of `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, each list in its order. This example has five: `baseline`, `liquidity-100m`, `holdings-50`, `rebalance-weeks-1`, and `slippage-050`. The smallest experiment is a baseline with no `variants`: the baseline and the default variant, two cases and 10 credits.

   [The experiment configuration](contracts.md#experiment-configuration) gives every key's rules.

2. Review the plan. Write the experiment under `runs/`, which the workspace's `.gitignore` keeps out of Git, because an experiment holds Portfolio123 data, as a run does:

   ```sh
   trialfolio run experiment.yaml --out runs/study/
   ```

   In a terminal, it shows the whole plan and asks you to type `approve`, as for a screen. The plan shows:

   - the experiment's ID, title, purpose, and prior research, which Trial Folio can't verify
   - the baseline's settings, once, with the provenance each value will have
   - each case, in the order it runs, with its key, its `case_id`, its change from the baseline, its description, and its request, exactly as it will be sent
   - the budget: the provider requests and authentication calls, and the credits at Portfolio123's documented cost
   - what's sent to Portfolio123, and what isn't, such as the experiment's ID, title, purpose, and prior research, and each case's key and description
   - the plan hash. One approval covers every case and the whole budget.

3. Type `approve`, or give the hash with `--approve sha256:<the plan hash>`. Trial Folio runs the cases one at a time, in order. It authenticates before the first request, and again only before a request that follows a 401 or 403, which drops its token. A case that fails is recorded, and the next one runs. Progress goes to the terminal.

When every case succeeds, it exits 0. When one doesn't, it exits 6, with `execution.partial`. The message lists each case that didn't succeed, with its outcome and error code, and gives the option that repeats each one awaiting a repeat: one whose request may have reached Portfolio123, and none of whose attempts succeeded ([repeating a case](#12-resume-repeat-or-revise-an-experiment)). A case whose response was saved but failed validation, `failed` with `provider.response_invalid`, has no tables and gets no option: its attempt succeeded, so the case is complete, and is never sent again. Its response stays in its attempt's folder, for you to [report](#14-when-something-goes-wrong). Either way, the run writes its report and manifest.

Two failures stop the run before its later cases, since each of those would fail the same way: Trial Folio's own authentication call failing, as with wrong credentials, and `provider.quota_exceeded`. The run ends with exit 6, and once you've fixed the cause, running the same command again runs the cases it didn't start.

An experiment's directory holds:

| Path | What it is |
|---|---|
| `experiment.lock` | The lock, which claims the directory for the experiment, so that only one process runs it at a time. It isn't evidence. |
| `plans/<n>/` | One for each plan you approved, numbered from 1: `configuration.yaml`, your configuration byte for byte; `plan.json`; and `experiment.json`, the experiment's research record as of that plan, with every plan before it and the reason for each revision |
| `cases/<case_id>/attempts/<attempt_id>/` | Each attempt's records, as a run's are. The attempt that authenticated also has `authenticating.json`. |
| `cases/<case_id>/normalized/` | The case's `metrics.csv` and `settings.csv`, as a run's, once its attempt succeeds |
| `sessions/<s>/` | One for each run of the command that passed its checks and its approval, numbered from 1: `session.json`, `report.html`, and `manifest.json`, which is written last |
| `logs/trialfolio.log` | The log of every session |

- **A case's folder is named by its `case_id`,** never its key. The plan display and the report give each case's key beside its `case_id`.
- **The newest session's report and manifest supersede the earlier ones.** A session without a manifest, because its command was interrupted, reads as incomplete until the same command resumes the experiment.
- **It isn't a run.** `trialfolio report` and `trialfolio review` read runs only, and fail with `input.not_a_run` given an experiment. Each session writes its own report.

**In the report** (`sessions/<s>/report.html`):

- The research notice, the Portfolio123 data statement, and "Not assessed", as in a run's report.
- The research context: the purpose, the prior research, and every plan, with its reason and what it changed.
- Each case's change from the baseline, and its coverage.
- The metrics side by side, with a column for each case that has results. The report computes no difference between cases, and orders, ranks, and marks no case by a value.
- The counts of cases and attempts; every case with its outcome and attempts; the cases awaiting a repeat, each with the option that repeats it; and the retired cases.
- In its limitations, that a prior-research declaration other than `complete` limits any claim drawn from the cases.

**Check:**

- Without approval, from a script, it fails with `plan.approval_required`, exit code 2, and shows only the plan hash and the budget: 6 provider requests, 30 credits. `runs/study/` doesn't exist.
- In a terminal, the plan lists the five cases in the order above, each with its `case_id`, the default `rebalance-weeks-1` among them.
- A budget below the number of cases fails with `config.invalid`, exit code 3, and the message gives the number of cases. So does a variant of `universe`, and the message names the settings a variant may change.
- Approved without credentials, it fails with `provider.auth_failed`, exit code 5. Nothing was sent, and `runs/study/` doesn't exist.
- When every case succeeds, stdout says "Experiment completed", the session, where its report is, the plan hash, and that statistical validation and trading readiness are not assessed. With exit code 6, stdout is empty, and the message on stderr lists the cases that didn't succeed.
- In the session's `manifest.json`, the planned cases equal those that succeeded, failed, were skipped, are unknown, and haven't run yet, and the report gives the same counts.
- Each case that succeeded has `metrics.csv` and `settings.csv` in its own `normalized/` folder, labeled with its `case_id`.
- The log names cases by their `case_id`, and holds no case key or description, formula, or result.

## 12. Resume, repeat, or revise an experiment

To go on with an experiment, run the same command again, into the same directory. Trial Folio reads and checks the experiment's records, then shows the plan with each case's outcome so far, and the budget counted so far. It needs the plan's approval again, by the same hash, so the same `--approve` approves it. Each run that's approved is a new session of the same experiment.

**Resume.** A resume treats each case by its state:

| State | What a resume does with it |
|---|---|
| **Complete:** one of its attempts succeeded, so its response was saved, even one that then failed validation | Skips it. It's never sent again. |
| **Due:** it has no attempt, or each failed before its request could reach Portfolio123, as after a failed authentication | Sends it |
| **Awaiting a repeat:** its request may have reached Portfolio123, and may have been charged, but none of its attempts succeeded. It's `unknown`, as after a timeout or an interrupt while waiting for Portfolio123, or `failed`, as after Portfolio123 rejected it. | Never sends it on its own. Only a repeat, below, sends it again. |

- **After an interrupt,** such as Ctrl-C, a storage failure, or a crash, the attempts recorded so far are kept. Run the same command again: it records what the stopped run left, such as an attempt interrupted while it waited for Portfolio123, which becomes `unknown`, writes the tables the stopped run didn't, and sends the cases that are due. If the first run was interrupted before its plan was recorded, nothing was sent, and the message says to remove the directory and run the command again.
- **A resume that sends nothing needs no credentials.** When no case is due and no repeat is to be made, it writes a new session's report and manifest, and sends nothing.
- **The records are checked first.** If one is missing or changed, as after an incomplete copy, the resume fails with `input.not_a_run`, exit code 3, and sends nothing.
- **One process at a time.** While one command runs the experiment, or waits for your approval, another fails with `experiment.locked`, exit code 4. Wait for the first to end, and run the command again.

**Repeat a case.** A case awaiting a repeat is sent again only when `--repeat` names it and you confirm that its request may be charged again. The plan display, the message of a run that leaves such a case, the report, and the [JSON summary](#13-use-it-from-a-script) each give its exact option:

```sh
trialfolio run experiment.yaml --out runs/study/ --repeat holdings-50
trialfolio run experiment.yaml --out runs/study/ --approve sha256:<the plan hash> --repeat holdings-50:<attempt-id>
```

- **In a terminal, without `--approve`, the key alone** asks you to type `repeat`, once you've approved the plan. The prompt lists each case to repeat, with its latest attempt whose request may have been charged, and the budget that would remain.
- **With the attempt ID,** the option is the confirmation, and Trial Folio doesn't ask. With `--approve`, or from a script, a repeat needs it.
- **Give `--repeat` once for each case** you repeat.
- **A repeat is a new attempt of the same case,** and counts against the budget. When the budget can't cover it, it doesn't start, and a revision that raises the budget lets the same option repeat it.
- **One confirmation, one repeat.** Once the repeat may have reached Portfolio123, running the same command again never repeats the case on the same confirmation:
  - **With the attempt ID,** it says the case was repeated already, and resumes the rest. A repeat that didn't succeed needs a new confirmation, which names the repeat's own attempt.
  - **With the key alone,** when the repeat succeeded, it says the case is complete, and resumes the rest. When the repeat didn't succeed, the case awaits a repeat again, and in a terminal the command asks you to type `repeat` again, for the repeat's own attempt: that's a new confirmation, and typing it repeats the case again.

Whether Portfolio123 charges for a request that fails is unknown, and an `unknown` request may have gone through. Before you repeat one, you can check your API credits on Portfolio123's website, as an interrupt's message suggests.

**Revise the plan.** After you change the configuration, the same command builds a new plan, a revision of the current one, and fails with `plan.changed`, exit code 3, until you give a reason and approve the revision:

```sh
trialfolio run experiment.yaml --out runs/study/ --revision-reason 'Raise the budget, and try 0.75% slippage.'
```

In a terminal, it shows the revision, with what changed and your reason, and asks you to type `approve`. Or give the revision's hash, which the `plan.changed` message gives, with `--approve`.

- **What revises the plan:** a change to a case's settings, an added or removed variant, a change to the budget, the title, the purpose, the prior research, a case's key or description, or the order of one setting's variants. So does a new version of Trial Folio, `p123api`, `requests`, or `urllib3`, even with the same configuration. A change the plan doesn't record, such as a comment, doesn't.
- **What a revision keeps.** A case whose settings didn't change keeps its `case_id` and its attempts, whatever its key, so a case that succeeded isn't sent again. A case whose settings changed is a new case, with a new `case_id`, even under the same key. The old case is retired: it and its attempts stay in the record, the report lists it, and the budget still counts its attempts.
- **The reason** is recorded in the new plan's `experiment.json`, and shown in the report. It's never sent or logged. Every revision needs one.
- **Running the approving command again** resumes the revised plan, as after an interrupt. A reason when there's no revision fails with `plan.approval_required`: check that the configuration is the file you changed.
- **Another experiment.** A configuration with another `experiment_id`, or whose baseline has another universe, is another experiment, not a revision. Run into this directory, it fails with `output.not_empty`: give it a new one.

[Running an experiment](contracts.md#running-an-experiment), [repeating a case](contracts.md#repeating-a-case), and [experiment plans and revisions](contracts.md#experiment-plans-and-revisions) give the rules.

**Check:**

- After a run that ends, the same command resumes. stderr says the plan is the experiment's current plan, plan 1, which this run resumes, and gives the provider requests counted so far. It skips the complete cases, and writes `sessions/2/`.
- A resume with no case due and no repeat to make sends nothing, needs no credentials, and writes its session's report and manifest.
- An `unknown` or rejected case isn't sent again without `--repeat`, and the plan display gives its option, `--repeat <case-key>:<attempt-id>`.
- `--repeat <case-key>` alone, with `--approve` or from a script, fails with `plan.approval_required`, exit code 2, and the message gives the option with the attempt ID. Nothing was sent.
- After a repeat confirmed by its attempt ID may have reached Portfolio123, the same command again says the case isn't repeated, because its confirmation was used, and sends nothing for it. A repeat that sent nothing, such as one whose authentication failed, leaves its confirmation unused, and the same command tries it again.
- A changed configuration fails with `plan.changed`, exit code 3, names the current plan, and gives the revision's hash. Nothing was sent or written.
- After a revision that changes a case's settings, the plan display and the report list the old case as retired, with its attempts.
- While a command waits for approval, the same command in another terminal fails with `experiment.locked`, exit code 4.

## 13. Use it from a script

Add `--json` to any command. stdout then holds exactly one JSON object, on success and on failure, and everything else goes to stderr. A usage error is the one failure without an object: an argument the parser rejects, such as a missing or blank `--out`, exits 2, reported on stderr, with stdout empty. The object gives the outcome, the exit code, the IDs, such as the plan hash, the output files, the counts, such as `provider_requests` and the credit `cost`, and the error, if any. For a review, `ids` holds the review ID, and `counts` the results, the flagged setting rows, the unavailable metric rows, and the warnings.

For an experiment:

- **`ids`** holds the `experiment_id`, the hash of the plan the command built, and the session's number, once each is known.
- **`cases`** lists each case of the plan, in its order, with its `case_key`, `case_id`, `outcome`, and `repeat_attempt_id`: the attempt ID that `--repeat <case-key>:<attempt-id>` names to repeat a case awaiting a repeat, or `null` for any other case.
- **`counts`** gives the experiment's counts, across every run of it: the cases by outcome, the retired cases, the attempts and the repeats, the provider requests and authentication calls, the cost, the unavailable metric rows, and this command's warnings.
- **`outputs`** gives the session's manifest and report.

Its schema is `schemas/json-summary-1.2.0.schema.json`, the version 0.3.0 writes for every command. Trial Folio 0.1.0 writes version 1.0.0, and 0.2.0 version 1.1.0, whose schemas, `schemas/json-summary-1.0.0.schema.json` and `schemas/json-summary-1.1.0.schema.json`, are kept beside it: each version only adds to the one before.

Approve only a plan you've reviewed. A script can read the hash from a run that wasn't approved, in `ids.plan_hash`, and approve it, but that skips the review the plan exists for. The same goes for a repeat: a script can read each case's `repeat_attempt_id` and repeat it, but each repeat may be charged again.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | The command completed. It says nothing about the strategy. |
| 1 | An unexpected internal error |
| 2 | A usage error, a plan not approved, or the license not acknowledged |
| 3 | An invalid configuration, input, artifact, or environment, or an experiment's changed plan whose revision wasn't approved with a reason |
| 4 | An output problem: the directory isn't empty, a write failed, or another process is running the experiment |
| 5 | A Portfolio123 error |
| 6 | An experiment ended with a planned case that didn't succeed. Every case is accounted for. |
| 130 | Interrupted, for example with Ctrl-C |

**Check:**

- `trialfolio demo --out demo2/ --json` prints one object with `"outcome": "completed"`.
- A plan run without approval, with `--json`, prints one object with `"exit_code": 2`, the plan hash in `ids`, and the error.
- An experiment's plan run without approval, with `--json`, also lists every case in `cases`. In a new experiment, each is `not_yet_run`.
- After a run of an experiment that leaves a case awaiting a repeat, `--json` gives that case's `repeat_attempt_id`, the one in the message's `--repeat` option.

## 14. When something goes wrong

Every error message says what failed, why, and what to do next. These are the ones you're most likely to see:

| Code | What happened | What to do |
|---|---|---|
| `config.invalid` | The configuration has a problem; the message lists each one | Fix them. Nothing was sent. |
| `output.not_empty` | `--out`, or the folder given to `trialfolio init`, names a directory that isn't empty. For an experiment, it holds something other than an experiment, or another experiment, with another `experiment_id` or universe. | Choose a new or empty directory |
| `plan.approval_required` | The plan wasn't approved, or the hash didn't match. For an experiment, also a `--repeat` that names no case awaiting a repeat, or that wasn't confirmed, or a `--revision-reason` with no revision. | Approve it in a terminal, or give its full hash. For a repeat, give the option the message shows. Nothing was sent. |
| `plan.changed` | An experiment's configuration, or the installed versions, changed since its current plan, and the revision wasn't approved with a reason | Give `--revision-reason`, and approve the revision's hash, which the message gives. Nothing was sent. |
| `experiment.locked` | Another process is running the experiment, or waiting for its approval | Wait for it to end, and run the command again. Nothing was sent. |
| `execution.partial` | An experiment ended with a planned case that didn't succeed; the message lists each one | Run the same command again to send the cases that are due, and repeat each case awaiting a repeat with the option the message gives |
| `artifact.unknown_schema_version` | A saved file's schema version is one this version of Trial Folio has no reader for | Read the run, or resume the experiment, with a version of Trial Folio that has one. Nothing was written, and a resumed experiment sends nothing. |
| `input.not_found`, `input.not_a_run` | `trialfolio report`'s run directory, or a review's `run` path, doesn't exist, or isn't a complete run. A review's message names the result. With `input.not_found`, it's also the configuration file given to `trialfolio run` or `trialfolio review`, which couldn't be read, as when it doesn't exist. | Give the output directory of a run that finished. Nothing was written. For the configuration file, check its path: nothing was sent or created. |
| `environment.unsupported` | The installed `p123api`, `requests`, or `urllib3` isn't the verified version, or `simplejson` is importable | Run `uv sync` in the repository to restore the locked versions. For `simplejson`, uninstall it from the environment, or run Trial Folio in its own virtual environment. |
| `provider.auth_failed` | The credentials are missing, or Portfolio123 refused them | Check the API ID and key |
| `provider.unavailable` | Portfolio123 couldn't be reached; the request wasn't sent | Try again later |
| `provider.request_rejected` | Portfolio123 answered the authentication call or the request with a status that no other code covers, such as a redirect, 404, or 429. The message gives the status. | After the authentication call, the request wasn't sent: try again later, and report it if it persists. After the request, it may have been charged: wait before running the command again, which is a new attempt. In an experiment, only a [repeat](#12-resume-repeat-or-revise-an-experiment) sends it again. |
| `provider.quota_exceeded` | Portfolio123 refused the request for quota or credits | Check your API credits. The request may have been charged. |
| `provider.unsupported_capability` | Portfolio123 rejected a setting; its own message follows | Change the setting. The request may have been charged. |
| `provider.outcome_unknown` | The request may have been sent and charged, but no response was saved, for example after a timeout | Trial Folio never resends it on its own. Running a screen's command again is a new attempt, and may be charged again. In an experiment, only a [repeat](#12-resume-repeat-or-revise-an-experiment) sends it again. |
| `provider.response_invalid` | A response was saved, but didn't have the expected layout | The response stays in the run. Report it, because Portfolio123's response may have changed. |
| `storage.write_failed` | A file couldn't be written durably, for example on macOS or Linux to an exFAT or FAT drive, which lacks hard links | Use another drive. If the request was sent, the attempt record says whether it may have been charged. |
| `command.interrupted` | You pressed Ctrl-C | The message says whether a request may have been sent. For an experiment, run the same command again to resume it. |
| `internal.unexpected` | A defect in Trial Folio | Report it, with the log the message names |

After a Portfolio123 error, the run's directory still has its report and manifest, which record the failure. After an interrupt, a storage failure, or an internal error, there's no manifest, so the run, or the review, reads as incomplete. An experiment's session is the same: it ends with its report and manifest even when cases fail, and without them after an interrupt, until the same command resumes the experiment. [Errors](contracts.md#errors) lists every code.

**Logs.** Each command with an output directory logs to `logs/trialfolio.log` there. `trialfolio init`, `trialfolio license`, and an internal error before the output directory is claimed log to a per-user directory, which the README's [Your data stays on your machine](../README.md#your-data-stays-on-your-machine) lists, with how to delete it. To see more detail, set `TRIALFOLIO_LOG_LEVEL=DEBUG`. At every level, logs hold no credentials, configuration values, formulas, or results.

**Reporting a problem.** [CONTACT.md](../CONTACT.md) links to a form for bugs and questions.
