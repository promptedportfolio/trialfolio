# Re-render a report

`trialfolio report` rebuilds a saved run's report offline, from its saved files. Use it when you want a run's report again, written into a new folder.

## Before you start

- **A run that finished,** written by `trialfolio run` or `trialfolio demo`. An experiment isn't a run: each of its sessions writes its own report, and `trialfolio report` fails with `input.not_a_run` given one.
- **No credentials.** It sends nothing to Portfolio123. Like `trialfolio run`, it needs your [acknowledgment of the license](../tutorials/first-backtest.md).

## Steps

1. From your workspace, give the run's directory, and a new or empty directory for the report:

    ```sh
    trialfolio report runs/first/ --out reports/first/
    ```

    The workspace's `.gitignore` keeps `reports/` out of Git, because a report holds Portfolio123 data.

2. Open `reports/first/report.html` in a browser.

## Check

- It exits 0, and writes only `reports/first/report.html` and its log. The run's directory isn't changed.
- The new report's values match the original's.
- A directory that isn't a complete run fails with `input.not_a_run`, and one that doesn't exist with `input.not_found`, both with exit code 3, and nothing is written.
