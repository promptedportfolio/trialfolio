# Use Trial Folio from a script

Use this page to run Trial Folio's commands from a script or a CI job, and read each command's result as one JSON object. It also shows how a script can approve a plan, or a repeat, without skipping its review.

## Before you start

A script has no terminal, so Trial Folio never asks it to type anything:

- **The license.** `run`, `report`, `demo`, and `review` need your acknowledgment of the license and the research notice. Read them first with `trialfolio license`. Then, in the script's environment, set `TRIALFOLIO_ACCEPT_LICENSE=LicenseRef-NSPRL-1.1/1.0`, which acknowledges them for each command that runs with it, and records nothing. Any value but the exact one is rejected, even after you've acknowledged, and an empty one counts as unset. Without an acknowledgment, the command fails with `license.not_acknowledged`, exit code 2, and writes nothing.
- **The plan.** When the command's error output isn't a terminal, it shows only the plan hash and the budget, never the formulas. When its input isn't a terminal, it doesn't ask for approval. Either way, without `--approve` it fails with `plan.approval_required`, exit code 2, with the exact `--approve` option in the message, and sends nothing. For a revision of an experiment's plan, it fails with `plan.changed`, exit code 3, instead, and the revision needs `--revision-reason` as well as its hash, which the message gives: [revise an experiment](revise-an-experiment.md).
- **Your credentials,** for a command that sends: [store your credentials](store-credentials.md) so that the script's commands get them.

## Steps

1. Add `--json` to any command. stdout then holds exactly one JSON object, on success and on failure, and everything else goes to stderr. The object gives the outcome, the exit code, the IDs, such as the plan hash, the output files, the counts, such as `provider_requests` and the credit `cost`, and the error, if any. [The JSON summary](../reference/json-summary.md) gives every field, and each schema version.

    One failure gives no object: an argument the command's parser rejects, such as a missing `--out`. That's a usage error, exit code 2, reported on stderr, and stdout is empty.

2. Review the plan in a terminal before the script approves it. Run the command there without `--approve`: it shows the full plan, with its hash, and asks you to type `approve`. Type anything else to stop, and nothing is sent.

3. Give the script the full hash you reviewed, exactly as shown:

    ```sh
    trialfolio run screen.yaml --out runs/first/ --approve sha256:<the plan hash> --json
    ```

4. Read the object's `outcome` and `exit_code`. Exit code 0 says the command completed, and nothing about the strategy. [Errors](../reference/errors.md) gives each exit code and error code.

!!! warning "Approve only a plan you've reviewed"
    A script can read the hash from a run that wasn't approved, in `ids.plan_hash`, and approve it, but that skips the review the plan exists for. The same goes for a repeat: a script can read each case's `repeat_attempt_id` and repeat it, but each repeat may be charged again.

## Repeat a case from a script

Without a terminal, `--repeat` needs the attempt ID: `--repeat <case-key>:<attempt-id>`. For an experiment, the object's `cases` gives each case's `repeat_attempt_id`, the attempt ID that repeats a case awaiting a repeat. [Repeat a case](repeat-a-case.md) gives the steps.

## Check

- `trialfolio demo --out demo2/ --json` prints one object with `"outcome": "completed"`.
- A plan run without approval, with `--json`, prints one object with `"exit_code": 2`, the plan hash in `ids`, and the error.
- An experiment's plan run without approval, with `--json`, also lists every case in `cases`. In a new experiment, each is `not_yet_run`.
- After a run of an experiment that leaves a case awaiting a repeat, `--json` gives that case's `repeat_attempt_id`, the one in the message's `--repeat` option.
