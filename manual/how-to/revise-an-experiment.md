# Revise an experiment

Use this page when you've changed an experiment's configuration after it ran, such as to raise its budget or try another variant. The same command then builds a new plan, a revision of the current one, and fails with `plan.changed`, exit code 3, until you give a reason and approve the revision.

## Before you start

- **The experiment's directory,** such as `runs/study/`, and its configuration file.
- **Your credentials,** when the revised plan has a case to send ([store your credentials](store-credentials.md)). A run that sends nothing needs none.

## Steps

1. Change the configuration. These revise the plan:
    - a change to a case's settings, an added or removed variant, a change to the budget, the title, the purpose, the prior research, a case's key or description, or the order of one setting's variants;
    - with a ranking definition, a change to the definition's file, its ranking method, or its source, such as a snapshot in the file's place;
    - a new version of Trial Folio, `p123api`, `requests`, or `urllib3`, even with the same configuration.

    A change the plan doesn't record, such as a comment, doesn't. Another `experiment_id`, or a baseline with another universe, is [another experiment](#another-experiment), not a revision.

2. Run the same command, into the same directory, with your reason:

    ```sh
    trialfolio run experiment.yaml --out runs/study/ --revision-reason 'Raise the budget, and try 0.75% slippage.'
    ```

3. In a terminal, it shows the revision, with what changed and your reason, and asks you to type `approve`. Or give the revision's hash, which the `plan.changed` message gives, with `--approve`:

    ```sh
    trialfolio run experiment.yaml --out runs/study/ --revision-reason 'Raise the budget, and try 0.75% slippage.' --approve sha256:<the revision's hash>
    ```

## The reason

- It's recorded in the new plan's `experiment.json`, and shown in the report. It's never sent or logged.
- Every revision needs one.
- It's 1 to 2,000 characters, not all whitespace.

## What a revision keeps

- **A case whose settings didn't change** keeps its `case_id` and its attempts, whatever its key, so a case that succeeded isn't sent again.
- **A case whose settings changed** is a new case, with a new `case_id`, even under the same key. The old case is retired: it and its attempts stay in the record, the report lists it, and the budget still counts its attempts.
- **With a ranking definition,** a changed definition changes every case whose definition changes with it: the baseline, each variant of another setting, and each ranking variant whose definition is then different. A ranking variant whose definition stays the same, byte for byte, keeps its case. A changed ranking method changes every case. A snapshot of the same definition in a file's place changes no case, and the revision records the new source ([plans with a ranking definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-with-a-ranking-definition)).
- **A ranking given another way,** such as a definition in a formula's place, is a changed setting of the baseline: the revision needs `schema_version: 1.1.0`, and its budget at least two requests a case.

A revision that raises the budget lets a [repeat](repeat-a-case.md) the budget couldn't cover go ahead, with the same option.

## Running the approving command again

Running the approving command again resumes the revised plan, as after an [interrupt](recover-from-an-interrupt.md).

A reason when there's no revision fails with `plan.approval_required`. Check that the configuration is the file you changed.

## Another experiment

A configuration with another `experiment_id`, or whose baseline has another universe, is another experiment, not a revision. Run into this directory, it fails with `output.not_empty`: give it a new one.

[Experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions) gives the rules.

## Check

- A changed configuration fails with `plan.changed`, exit code 3, names the current plan, and gives the revision's hash. Nothing was sent or written.
- After a revision that changes a case's settings, the plan display and the report list the old case as retired, with its attempts.
