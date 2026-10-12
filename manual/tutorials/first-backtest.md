# Your first backtest

This tutorial takes you from setting up Trial Folio to reading the report of your first screen backtest. On the way, you try the demo, look at a screen configuration, and review the plan Trial Folio builds from it before anything is sent.

## What you need

For part 1:

- `git`
- [`uv`](https://docs.astral.sh/uv/)
- Python 3.12 or later. If you don't have it, `uv python install 3.12` installs it.

Part 1 needs no Portfolio123 subscription or credentials. Once Trial Folio is set up, it runs offline, and it sends nothing to Portfolio123.

Part 2 sends one backtest request to Portfolio123. It also needs:

- a Portfolio123 subscription with the appropriate access
- your Portfolio123 API ID and key
- at most 5 API credits, Portfolio123's documented cost of one screen backtest

The commands are for macOS and Linux shells. So far, Trial Folio has been tested on macOS only. To see a command's exit code, run `echo $?` right after it.

## Part 1: Without a subscription

### Step 1: Get Trial Folio

Until Trial Folio is released as a package, you run it from a copy of its repository.

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

    Add the line to your shell's startup file, such as `~/.zshrc`, to keep it. The rest of this manual writes `trialfolio` for this command. If you later keep your API key in your system's keychain, [storing your credentials](../how-to/store-credentials.md) replaces this alias with a function.

3. Check the command:

    ```sh
    trialfolio --version
    trialfolio --help
    ```

    `trialfolio --version` prints the version of the tag your copy came from, such as `trialfolio 0.2.1` from `v0.2.1`. A copy of `main`, like the one you just cloned, prints the version of the latest release whose specification is complete, which may not be tagged yet ([D-26](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).

    `trialfolio --help` lists the commands `init`, `run`, `report`, `demo`, `review`, and `license`.

### Step 2: Set up a workspace

A workspace is a folder of your own, outside the repository, for your configurations and runs. You run Trial Folio's commands from there.

1. Set up a workspace:

    ```sh
    trialfolio init ~/research
    ```

    It exits 0, without asking you to acknowledge the license: it needs no acknowledgment, and sends nothing. It writes three files:

    - `screen.yaml`, a starter configuration
    - `README.md`, the next steps
    - `.gitignore`, which keeps credential files, runs, reports, and reviews out of Git, if you keep the folder in a repository

    The folder must be new or empty. Given no folder, `trialfolio init` sets up the current one.

2. Go to the workspace, and list what it holds:

    ```sh
    cd ~/research
    ls -A
    ```

    It holds exactly `screen.yaml`, `README.md`, and `.gitignore`, with no `logs/` folder.

3. Run the same `trialfolio init ~/research` again. It fails with `output.not_empty`, exit code 4, and changes nothing.

### Step 3: Acknowledge the license

`run`, `report`, `demo`, and `review` need a one-time acknowledgment of the license and the research notice. `--version`, `--help`, `trialfolio init`, and `trialfolio license` don't. Until you acknowledge, `trialfolio demo --out demo/` run from a script, or with its input redirected, fails with `license.not_acknowledged`, exit code 2, and writes nothing.

1. Read the license and the research notice:

    ```sh
    trialfolio license
    ```

    It prints the license, the full research notice, and whether you've acknowledged them.

2. Acknowledge them:

    ```sh
    trialfolio license --accept
    ```

3. Check that it's recorded:

    ```sh
    trialfolio license | tail -n 1
    ```

    The last line says "Acknowledged", with the time and the file it's recorded in. The record holds only the license identifier, the notice version, the time, and how you acknowledged.

You can acknowledge in two other ways. The first time you run `run`, `report`, `demo`, or `review` at a terminal, it shows the concise notice and asks you to type `accept`. Or set `TRIALFOLIO_ACCEPT_LICENSE=LicenseRef-NSPRL-1.1/1.0` for one command, which records nothing, and suits scripts. Any other value of `TRIALFOLIO_ACCEPT_LICENSE` is rejected, even after you've acknowledged, and an empty one counts as unset. [The commands reference](../reference/cli.md) describes the three ways.

A new version of the license asks again. Release 0.2.1 brings version 1.1, so an acknowledgment of version 1.0, from 0.1.0 or 0.2.0, doesn't cover it.

### Step 4: Try the demo

The demo writes a complete example run from invented values. It needs no Portfolio123 subscription or credentials, and sends nothing.

1. Run it:

    ```sh
    trialfolio demo --out demo/
    ```

    It exits 0. Its last lines say the synthetic run was written, that nothing was sent to Portfolio123 and every value is invented, where the report is, the plan hash, and that statistical validation and trading readiness are not assessed.

    Synthetic example output from `trialfolio demo`:

    ```text
    Synthetic example run written to demo/. Nothing was sent to Portfolio123: every value is invented.
    Report: demo/report.html
    Plan hash: sha256:c10831d21f098224d7ddcc68c25cc818585839cde0dfe8ac4890cbfd6d41ec93
    Statistical validation and trading readiness: not assessed.
    ```

    A plan's hash changes with the versions of Trial Folio and of the packages that send its requests, so yours may differ.

2. Open `demo/report.html` in a browser. On macOS, `open demo/report.html` opens it.

    Its title starts with "Synthetic example", and it says nothing was sent or charged. Apart from that, it's the report a real run writes, which [step 9](#step-9-read-the-results) walks through.

3. List what `demo/` holds, with `ls -R demo`. It holds the files [a run holds](#step-9-read-the-results).

### Step 5: Look at the screen configuration

A screen configuration is a YAML file describing one long-only stock screen backtest. Your workspace's `screen.yaml` is one. It has the settings of this example, which Portfolio123 accepted in a live call, with a comment on each key:

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

In `screen.yaml`, the `purpose` line starts with `#`, so it's a comment until you remove the `#`. As you read the file, notice:

- **Every key but `purpose` and `data_vendor` is required.** There's no default end date, and no default slippage of zero.
- **Text that Portfolio123 receives goes in single quotes:** the rules, the ranking's formula or name, the universe, and the benchmark. Without quotes it's rejected, because outside quotes YAML reads a space and `#` as the start of a comment, with no error. It would cut `FRank("EarnYield", #Industry) > 50` short, and read `name: Core Combo #2` as `Core Combo`, a different ranking system. Single quotes also keep the double quotes inside a formula as they are. Double quotes and block scalars (`|`) work too.
- **Other values need no quotes:** numbers, dates, `true` and `false`, fixed words such as `screen`, `open`, and `complete`, and the title and purpose, which are never sent. A title or purpose that holds a space followed by `#` still needs quotes, or YAML cuts it short.
- **Comments** run from `#` to the end of the line, outside quotes. They aren't part of the plan, so they don't change its hash, and the run keeps them in its copy of the file.
- **`data_vendor`** may be left out, as here, or given as `FactSet`. Either way it's recorded as FactSet, an inferred default, and isn't sent.
- **Only verified values are accepted.** Portfolio123 documents other values, such as other rebalance frequencies. Trial Folio rejects them until a live call verifies them.

A ranking can also be an existing ranking system in your account, by name or by ID, in place of the formula:

```yaml
ranking:
  name: 'My ranking system'
```

```yaml
ranking:
  id: 12345
```

A ranking system, like the universe, can change in your account after the run, and Trial Folio doesn't save its definition. So the run records it as not snapshotted, and its reproducibility as incomplete. A formula ranking is recorded completely. [Reproducibility](../explanation/reproducibility.md) explains why that matters, and [the screen configuration reference](../reference/screen-configuration.md) gives every key's rules.

Now see how Trial Folio reports a mistake:

1. In `screen.yaml`, change `rebalance_weeks: 4` to `rebalance_weeks: 2`.
2. Run the configuration:

    ```sh
    trialfolio run screen.yaml --out runs/first/
    ```

    It fails with `config.invalid`, exit code 3, and the message says "`rebalance_weeks` input should be 1 or 4." The message lists every problem, and nothing is sent or created. A misspelled key or a missing required key fails the same way.

    A rule without quotes, such as `- AvgDailyTot(30) > 1000000`, fails the same way, with "`rules[0]` is text Portfolio123 receives, written without quotes." So does `universe: SP500`, naming `universe`.

3. Change `rebalance_weeks` back to `4`.

### Step 6: Review the plan

Before anything is sent, Trial Folio builds a plan from the configuration and shows it. Reviewing it needs no credentials, and creates nothing.

1. In a terminal, run the configuration:

    ```sh
    trialfolio run screen.yaml --out runs/first/
    ```

    It shows the full plan, and asks you to type `approve`. The plan shows:

    - the request, exactly as it will be sent
    - every setting, with the provenance each value will have, marking inferred defaults, settings not snapshotted, commission not modeled, and parameters not sent
    - the budget: at most 1 request, 5 credits at Portfolio123's documented cost, and that a request that reaches Portfolio123 may be charged even if it fails
    - what's sent to Portfolio123, and what isn't
    - the plan hash, `sha256:` and 64 hex digits

2. Read the plan, then type anything else, such as `stop`, to stop.

    It fails with `plan.approval_required`, exit code 2. `runs/first/` doesn't exist, and the message says nothing was sent.

3. See what a script would see. Pipe the command's output through `cat`, so its error output isn't a terminal. After a pipe, `echo $?` gives `cat`'s exit code, so the parentheses print the command's own:

    ```sh
    (trialfolio run screen.yaml --out runs/first/ 2>&1; echo "Exit code: $?") | cat
    ```

    When its error output isn't a terminal, as in a script, it shows only the plan hash and the budget, never the formulas. When its input isn't a terminal, it doesn't ask. Either way, it fails the same way, with `plan.approval_required`, exit code 2, and the exact `--approve` option in the message.

4. Change a comment in `screen.yaml`, such as the one after `max_holdings`. Run step 3's command again, with `--out runs/other/` in place of `--out runs/first/`.

    The plan hash is the same. The same configuration, with the same versions of Trial Folio, `p123api`, `requests`, and `urllib3`, gives the same plan hash every time, in any output directory, and adding or changing a comment doesn't change it. After you upgrade any of them, the same configuration needs approving again.

5. Give the backtest a purpose. Remove the `#` and the space at the start of the `purpose` line, and write why you're running this backtest after `purpose:`. Run step 3's command again.

    The plan hash changes. Changing a setting, the title, or the purpose changes it, so an approval covers only the plan you reviewed. [Plans and approval](../explanation/plans-and-approval.md) explains why Trial Folio works this way.

## Part 2: With a subscription

From here on, you need your Portfolio123 subscription and credentials, and the run uses at most 5 API credits.

### Step 7: Set your credentials

Trial Folio reads your API ID and key from two environment variables, `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`. Portfolio123's website lists both under DataMiner & API. Trial Folio never reads them from a file, and never saves or logs them.

The quickest way is to type them at a prompt, for one shell session. To keep them in your system's keychain or your password manager instead, so you don't type them each time, follow [Store your credentials](../how-to/store-credentials.md). Keep the key out of your shell's history, and out of any plain-text file.

1. In the terminal you'll run the backtest from, type each value at a prompt that doesn't show the key. Each `read` waits for you to type a value and press Return:

    ```sh
    read -r TRIALFOLIO_P123_API_ID
    read -rs TRIALFOLIO_P123_API_KEY
    export TRIALFOLIO_P123_API_ID TRIALFOLIO_P123_API_KEY
    ```

    They last until you close the terminal. `unset TRIALFOLIO_P123_API_ID TRIALFOLIO_P123_API_KEY` removes them sooner.

If they're missing, an approved plan fails with `provider.auth_failed`, exit code 5. The message names the missing variables, and says nothing was sent and no output was created.

### Step 8: Run the backtest

A run sends one request, which costs 5 API credits.

!!! warning "May be charged"
    A request that reaches Portfolio123 may be charged even if it fails. Trial Folio never resends a request on its own: running the command again is a new attempt. [Credits and uncertain charges](../explanation/credits-and-uncertain-charges.md) explains why.

1. Run the configuration in a terminal, review the plan, and type `approve`:

    ```sh
    trialfolio run screen.yaml --out runs/first/
    ```

    Or, for a plan you've already reviewed, give its hash:

    ```sh
    trialfolio run screen.yaml --out runs/first/ --approve sha256:<the plan hash>
    ```

    The full hash, exactly as shown, runs without asking. An abbreviated or different hash fails with `plan.approval_required`, and sends nothing. `--out` must name a new or an empty directory: Trial Folio never overwrites anything.

2. Wait. Progress goes to the terminal, including how the attempt ended and whether it may have been charged.

    It exits 0. The attempt line says it succeeded, possibly charged, with its attempt record written. stdout says "Run completed", where the report is, the plan hash, and that statistical validation and trading readiness are not assessed.

3. Run the same command again. It fails with `output.not_empty`, exit code 4, before the plan is shown, and changes nothing in `runs/first/`.

If the run fails, its message says what failed, why, and what to do next. [Errors](../reference/errors.md) lists each code.

### Step 9: Read the results

Your run's directory, `runs/first/`, holds:

- `report.html`, the report
- `normalized/metrics.csv` and `normalized/settings.csv`, the normalized tables
- `manifest.json`: what ran and how, its outcome and counts, its reproducibility, and every file's hash
- `plan.json`, the plan you approved, with the versions of the packages that sent it
- `configuration.yaml`, your configuration file, byte for byte
- `cases/<case>/attempts/<attempt>/`, the attempt's records: `started.json`, `attempt.json`, the request without credentials, and Portfolio123's decoded response
- `logs/trialfolio.log`, the run's log

[Outputs](../reference/outputs.md) describes each file. Without a subscription, you can follow these steps in `demo/`, which holds the same files, with invented values.

1. Open `runs/first/report.html` in a browser. It's one self-contained file, with no scripts, that opens offline.

    - The research notice is at the top, with a link to the full notice at the end.
    - Its ten sections say what a screen backtest can and can't support. A section the run can't support says so, and why.
    - A value missing from the response shows as unavailable, with the reason, never as zero.
    - Commission shows as not modeled: the API documents no commission setting, and slippage is the only cost sent.
    - If the response covers different dates than you asked for, the report shows both, and `settings.csv` flags the date as `coverage_mismatch`.
    - Statistical validation and trading readiness read "Not assessed".
    - The closing section carries the Portfolio123 data statement and two outside links: the license and Portfolio123's terms. The license link names the tag of the version that rendered the report, such as `v0.1.0`, so it works only once that version is tagged.

    [What a backtest can support](../explanation/what-a-backtest-can-support.md) explains why the report says what it can't support.

2. Open `runs/first/normalized/metrics.csv` in a spreadsheet or a text editor. It has 20 rows: the response's coverage, its first date, last date, and number of periods, then the strategy's and the benchmark's metrics, with units and source precision. The report's values match it.

3. Open `runs/first/normalized/settings.csv`. It has 23 rows, the 23 settings, each with its value, provenance, and flags:

    - commission is `not_modeled`
    - `data_vendor` and `risk_stats_period` are flagged `inferred_default`
    - five parameters are `not_sent`, with `unknown` provenance
    - the universe, and a ranking by name or ID, are flagged `not_snapshotted`

    [The flag codes](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#flag-codes) explain each flag.

4. Open `runs/first/manifest.json`. Its reproducibility is `incomplete`: the universe isn't snapshotted, and neither is a ranking by name or ID. The manifest is written last, so a run without one is incomplete.

5. Open `attempt.json`, in `runs/first/cases/<case>/attempts/<attempt>/`. It gives the outcome, `possibly_charged`, and the cost Portfolio123 reported. The demo's gives no cost, since nothing was charged.

6. Open the log, `runs/first/logs/trialfolio.log`. It holds no credentials, configuration values, formulas, or results.

## Next steps

- Run a baseline screen and a few variants of it under one plan: [Your first experiment](first-experiment.md).
- Keep your credentials in your keychain or password manager: [Store your credentials](../how-to/store-credentials.md).
- Rebuild a saved run's report offline: [Re-render a report](../how-to/re-render-a-report.md).
- Compare two runs: [Compare runs](../how-to/compare-runs.md).
