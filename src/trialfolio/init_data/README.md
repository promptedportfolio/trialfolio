# Trial Folio workspace

`trialfolio init` set up this folder for your screen configurations and the runs Trial Folio writes from them. Run Trial Folio's commands from here.

- `screen.yaml` is a screen configuration to change for your own backtest. It starts with the settings of the example Portfolio123 accepted in a live call.
- `.gitignore` matters if you keep this folder in Git. It keeps credential files out, and runs, reports, and reviews too, because they hold Portfolio123 data.

## Next steps

1. Read the license and the research notice with `trialfolio license`, and acknowledge them with `trialfolio license --accept`.
2. Try the demo, which sends nothing and needs no credentials: `trialfolio demo --out demo/`.
3. Change `screen.yaml`. Write every formula in single quotes.
4. Set your Portfolio123 API ID and key in `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`.
5. Run it: `trialfolio run screen.yaml --out runs/first/`. Trial Folio shows the plan, with the exact request and its cost, 5 API credits, and sends nothing until you type `approve`.
6. Open `runs/first/report.html`.

The [user guide for this version](https://github.com/promptedportfolio/trialfolio/blob/v{version}/docs/user-guide.md) explains each step, how to set your credentials without saving the key in your shell's history, and what to check.
