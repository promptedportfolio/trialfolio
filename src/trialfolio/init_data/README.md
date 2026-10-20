# Trial Folio workspace

`trialfolio init` set up this folder for your configurations and what Trial Folio writes from them: runs, reports, reviews, and experiments. Run Trial Folio's commands from here.

- `screen.yaml` is a screen configuration to change for your own backtest. It starts with the settings of the example Portfolio123 accepted in a live call.
- `.gitignore` matters if you keep this folder in Git. It keeps credential files out, and runs, reports, and reviews too, because they hold Portfolio123 data.

## Next steps

1. Read the license and the research notice with `trialfolio license`, and acknowledge them with `trialfolio license --accept`.
2. Try the demo, which sends nothing and needs no credentials: `trialfolio demo --out demo/`.
3. Change `screen.yaml`. Write every formula in single quotes.
4. Set your Portfolio123 API ID and key in `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`.
5. Run it: `trialfolio run screen.yaml --out runs/first/`. Trial Folio shows the plan, with the exact request and its cost, 5 API credits, and sends nothing until you type `approve`.
6. Open `runs/first/report.html`.

## After your first run

- Compare saved runs with a baseline you choose: write a review configuration, and run `trialfolio review`.
- Run an experiment, a baseline screen and a few variants of it under one plan and one budget: write an experiment configuration, and run it into a folder under `runs/`, such as `trialfolio run experiment.yaml --out runs/study/`. Running the same command again resumes it.

The [user manual](https://promptedportfolio.github.io/trialfolio/) explains each step, how to set your credentials without saving the key in your shell's history, and what to check. It describes Trial Folio as its repository's `main` branch has it. The manual's pages for this version, {version}, are [at its tag](https://github.com/promptedportfolio/trialfolio/blob/v{version}/manual/index.md).
