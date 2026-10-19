# Plans and approval

Trial Folio sends nothing to Portfolio123 until it has built a plan, shown it to you, and you've approved it. This page explains what the plan holds, how its hash identifies it, and why approval works the way it does.

## Why a plan comes first

Every request Trial Folio sends to Portfolio123 can use API credits, and may be charged even if it fails ([credits and uncertain charges](credits-and-uncertain-charges.md)). So before anything is sent, Trial Folio builds a plan from your configuration and shows it: exactly what would be sent, and the most it can cost. Nothing is sent until you approve that plan. This is one of Trial Folio's enduring requirements, [REQ-04](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements): no charged or mutating provider request may run without an approved plan, identified by its hash.

Only one command can send anything: `trialfolio run`, given a screen or an experiment configuration ([D-24](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)), or, from release 0.4.0, a ranking snapshot configuration, which reads a ranking system saved in your account with one `rank_get`, under a plan of its own, and writes nothing to it ([D-36](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). No other command sends anything: `report`, `review`, and `demo` work offline.

`trialfolio run` puts the plan before everything that costs or creates anything. It checks the license acknowledgment, the configuration, the output directory, and the installed versions, then builds the plan and shows it. Only after you approve does it check your credentials, and only then does it create the output directory and send anything ([order of steps](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#approval)). So reviewing a plan needs no credentials, and creates nothing.

For an experiment, the plan also fixes the research before any result exists. Trial Folio compiles every case into fully resolved settings before it sends anything, and records the plan in the experiment's directory before the first request. So the cases are set before you see any of their results, as [release 0.3.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#referenced-requirements) requires, citing [METH-02.5](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-02-separate-development-selection-and-confirmation) and [METH-06.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-06-robustness-and-economic-usefulness).

## What the plan shows

For a screen configuration, the full plan shows:

- the title and purpose, which are never sent;
- the request, exactly as it will be sent;
- every setting, with the provenance each value will have, marking inferred defaults, settings not snapshotted, commission not modeled, and parameters not sent ([reproducibility](reproducibility.md));
- the budget: at most 1 request, 5 credits at Portfolio123's documented cost, and that a request that reaches Portfolio123 may be charged even if it fails. It also gives the most authentication calls, whose cost isn't documented ([credits and uncertain charges](credits-and-uncertain-charges.md#the-budget));
- the retry policy: Trial Folio never resends a request on its own;
- what's sent to Portfolio123, and what isn't;
- the plan hash, `sha256:` and 64 hex digits, and how to approve it.

Nothing in a plan has been sent yet, so no value in it is verified. Each setting shows its expected provenance instead: the provenance it will have once the request is sent.

What leaves your machine falls into three categories, each sent to Portfolio123 through `p123api`: your credentials, to authenticate, which are never recorded; the strategy definition, meaning the universe, the rules, and the ranking; and the backtest settings. Nothing else is sent: not the title, the purpose, `data_vendor`, the configuration file, file paths, earlier results, or logs ([data sent](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#data-sent)).

Text from your configuration, such as a title or a formula, is shown with its control and formatting characters written as escapes, such as `\u001b`. So that text can't move the cursor, clear the terminal, or reorder what the plan shows.

For an experiment, the plan shows the whole experiment at once:

- its ID, title, purpose, and prior research, which Trial Folio can't verify;
- the baseline's settings, once, with the provenance each value will have;
- each case, in the order it runs, with its key, its `case_id`, its change from the baseline, its description, and its request, exactly as it will be sent;
- the budget: the provider requests and authentication calls, and the credits at Portfolio123's documented cost;
- what's sent to Portfolio123, and what isn't, such as the experiment's ID, title, purpose, and prior research, and each case's key and description;
- the plan hash.

When you run the same command again, to go on with an experiment, the plan also shows each case's outcome so far and what this run will do with it, the retired cases, and the budget counted so far ([experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)).

From release 0.4.0, a screen or an experiment whose ranking is a ranking system's definition, in a file or a ranking snapshot, sends each case's definition to Portfolio123 before its backtest, so its plan shows more ([plans with a ranking definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-with-a-ranking-definition)):

- that the run overwrites `ApiRankingSystem`, a ranking system in your Portfolio123 account, with each case's definition, just before its backtest, which ranks by that system's name; that a lock keeps other Trial Folio processes on your machine from writing it meanwhile, but only those that lock the same file, not one that sees another `/tmp`, such as in a container, or one with another `TRIALFOLIO_LOCK_DIR`; and that nothing keeps Portfolio123's website, or another machine, from writing or using it at the same time;
- where the definition came from: a file, by the definition's hash, or a snapshot, by its system's name and when it was read;
- each node's weight, among the baseline's settings, and each variant's change;
- each case's `rank_update`, the request that writes its definition, with the whole definition, line by line, and its hash, before its backtest;
- the budget: two requests a case, a `rank_update` at 1 credit and a backtest at 5, at Portfolio123's documented costs, so 6 credits a case.

## The plan hash

The plan hash is `sha256:` followed by 64 lowercase hex digits: the SHA-256 of the plan's canonical form, under [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) ([plan hashing](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-hashing)). It's the plan's identity, and it's what you approve.

A plan holds nothing that varies between invocations: no timestamps, output directory, file paths, attempt IDs, credentials, or account information. So the same configuration, with the same versions of Trial Folio, `p123api`, `requests`, and `urllib3`, gives the same plan and the same hash every time, on any machine, and for any output directory. That's what lets you review a plan in one command and approve it in the next.

Comments aren't part of the plan, so adding or changing one doesn't change the hash. Nor does anything else about how the file is written: an omitted `data_vendor` and an explicit `FactSet` give the same plan, and so do `0.250` and `0.25`. The run still keeps your file, comments and all, in its byte-for-byte copy ([reproducibility](reproducibility.md#the-configuration-byte-for-byte)).

Anything the plan does hold changes the hash, and needs a new approval:

- a setting, the title, or the purpose;
- for an experiment, its prior research, its budget, a case's key or description, or the order of one setting's variants;
- the version of Trial Folio, `p123api`, `requests`, or `urllib3`. So after you upgrade any of them, the same configuration needs approving again ([reproducibility](reproducibility.md#the-plans-package-versions)).

An experiment's later plans also record the plan they revise, so the hash depends on the experiment's history too. The same configuration, versions, and history still give the same hash, so a revision, too, can be reviewed in one command and approved in the next.

A saved plan is checked against its hash too. Anything that reads a saved run, such as `trialfolio report`, computes the hash of its `plan.json` again. If it differs from the hash the plan records, the run is invalid, with `input.not_a_run`.

## Approving a plan

You approve a plan in one of two ways ([approval](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#approval)):

- **In a terminal.** Without `--approve`, when both the command's input and its error output are a terminal, Trial Folio shows the full plan and asks you to type `approve`. The answer must be exactly `approve`: lowercase, with nothing before or after it. Anything else, an empty line, or the end of input is a refusal. When you approve, Trial Folio passes on the hash of the plan it showed you.
- **By its hash.** For a plan you've already reviewed, `--approve` gives its hash, such as `--approve sha256:<the plan hash>`. With `--approve`, Trial Folio never asks.

Either way, the approval is checked against the plan itself. Trial Folio computes the plan's hash from its contents, and runs the plan only when it's given a hash equal to that one. It never trusts a hash stored in a file. That's why `--approve` takes only the full hash, exactly as shown: an abbreviated, malformed, or different hash isn't equal to the plan's, so it doesn't match. And since any change to the plan changes its hash, an approval of one plan never covers another.

Without a match, the command fails with `plan.approval_required`, exit code 2, or, for a revision of an experiment's plan, with `plan.changed`, exit code 3 ([below](#one-approval-for-a-whole-experiment)). It creates no output directory, and sends nothing, and the message says nothing was sent. The run's manifest records how its plan was approved, `interactive` or `option`.

## What a script sees

The full plan holds your configuration's values and formulas, which Trial Folio keeps out of its logs ([REQ-06](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements)). So the plan display is written directly to stderr, the command's error output, never through logging, and Trial Folio shows the full plan only when that output is a terminal.

When the error output isn't a terminal, as in a script or a CI job whose output may be kept, Trial Folio shows only the plan hash and the budget, never the formulas, and says that running the command in a terminal shows the full plan. For an experiment it also gives, when you go on with one, whether the plan is the current plan or a revision of it, and the counts so far: nothing from the configuration. With a matching `--approve`, the plan is already approved, so Trial Folio shows only the hash and the budget there too. For a plan with a ranking definition, both add one line, that the run overwrites `ApiRankingSystem` in your account, which holds nothing from the configuration.

When the input isn't a terminal, Trial Folio doesn't ask. Without `--approve`, the command fails with `plan.approval_required`, or `plan.changed` for a revision, and the message gives the exact `--approve` option for this plan, with `--revision-reason` for a revision. With `--json`, the summary's `ids` hold the plan hash ([JSON summary](../reference/json-summary.md)). So a script can get a plan's hash without sending anything ([using Trial Folio from a script](../how-to/use-from-a-script.md)).

## Approve only a plan you've reviewed

A script can read the hash of a plan that wasn't approved, from the summary's `ids.plan_hash`, and approve it in its next command. That works, but it skips the review the plan exists for. Trial Folio can't tell whether anyone read the plan: approving it is your decision that this request, at this cost, should be sent.

The same goes for a repeat in an experiment. A script can read each case's `repeat_attempt_id` from the summary and repeat that case, but each repeat may be charged again ([why a repeat needs a confirmation](credits-and-uncertain-charges.md#why-a-repeat-needs-a-confirmation)).

## One approval for a whole experiment

An experiment has one plan, covering every case and the whole budget, and one approval covers all of it. Trial Folio never asks case by case ([release 0.3.0's required behavior](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#required-behavior), 1).

To go on with an experiment, after it ends or is interrupted, you run the same command again, into the same directory. That run needs the plan's approval again, by the same hash, as every `run` that sends does. So the same command, with the same `--approve`, resumes it, and in a terminal you see its progress before you confirm. Each run that's approved is a new session of the same experiment. An approval recorded in the directory, for later runs to reuse, would send without asking, so each run asks again ([open questions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#open-questions)).

When you change the configuration, or upgrade Trial Folio, `p123api`, `requests`, or `urllib3`, the same command builds a new plan, a revision of the current one. A revision needs two things: a reason, given with `--revision-reason`, and the approval of the revision's hash, in a terminal or with `--approve`. Without both, the command fails with `plan.changed`, exit code 3, and sends and writes nothing. Its message gives the revision's hash. A revision without a reason fails without asking, even in a terminal, since no answer could approve it ([approving a revision](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)).

Every revision needs a reason, a change of versions included, so the experiment's record says why each plan replaced the one before it. The reason is recorded in the new plan's `experiment.json` and shown in the report. It's never sent or logged. A reason given when there's no revision fails with `plan.approval_required`: a reason for a change that isn't there suggests that the configuration you gave isn't the file you changed. The one exception is the command that approved a revision, run again with the same reason: it resumes the revised plan, as after an interruption.

A case awaiting a repeat is sent again only with its own confirmation, after the plan's approval ([why a repeat needs a confirmation](credits-and-uncertain-charges.md#why-a-repeat-needs-a-confirmation)). To revise an experiment step by step, see [revising an experiment](../how-to/revise-an-experiment.md).

## Where it's specified

- [Plans and approval](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-and-approval), in contracts.md: the plan's contents, the budget, the data sent, hashing, approval, and the plan display.
- [Experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions), in contracts.md: an experiment's plan, revisions, and the approval of a resume.
- [REQ-04](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements) and [D-24](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions), in spec.md.
- [Release 0.3.0's required behavior](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#required-behavior), for compiling and approving an experiment.
