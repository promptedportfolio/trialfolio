# Reproducibility

A Trial Folio run records what was planned, what was sent, and what came back, so you can see exactly what ran. This page explains what a run records, what it can't, and why.

## What reproducible means here

Portfolio123's data and engine change, so running the same backtest again may give different results. What Trial Folio keeps instead is the evidence of each run: your configuration, the plan you approved, the request it sent, and the response it saved. From those, it regenerates the analysis and the report offline, with identified code and settings, without asking Portfolio123 again ([INV-05](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants), [METH-05.7](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-05-data-integrity-appropriate-to-the-claim)). That's how `trialfolio report` re-renders a saved run's report, sending nothing and needing no credentials ([re-rendering a report](../how-to/re-render-a-report.md)).

Running a screen configuration again, into a new directory, is a new attempt of the same case. It never replaces the earlier run ([ADR 0003](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0003-versioned-research-artifacts.md)).

## Where each value came from

Every setting, metadata value, and metric Trial Folio records carries its provenance: where the value came from ([INV-02](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants), [provenance](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#provenance)).

| Provenance | Meaning |
|---|---|
| `verified` | Sent to Portfolio123 in a request Trial Folio executed, or captured from Portfolio123 during that attempt |
| `user_supplied` | Given by you as description, not as a setting, such as a title, a purpose, or a revision's reason |
| `inferred` | Derived by Trial Folio under a documented rule, which the record gives |
| `unknown` | Not available from any source |

Trial Folio holds only Portfolio123 results that come from requests it planned, sent, and recorded itself, so the settings it sent and the values it captured are `verified` ([ADR 0005](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0005-build-on-the-portfolio123-api-only.md)). Before anything is sent, the plan shows each setting's expected provenance: the one it will have once the request is sent.

## Inferred defaults and settings not sent

Trial Folio never fills a gap with zero or a favorable default without saying so ([INV-03](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants), [METH-01.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-01-define-the-question-before-measuring-success)). Where a setting's value doesn't come from the request, `settings.csv` says where it does come from. Of a run's 23 settings rows ([screen settings](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#screen-settings)):

- **`data_vendor`** is `FactSet`, `inferred`, and flagged `inferred_default`, whether you leave it out or give it. FactSet is the only supported vendor ([D-16](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). The endpoint documents no vendor parameter, so it's never sent, and the response doesn't report the vendor, so it stays inferred.
- **`risk_stats_period`** is `monthly`, `inferred`, and flagged `inferred_default`. Trial Folio doesn't send that parameter, so Portfolio123's documented default applies.
- **`commission`** is `not_modeled`, `inferred`: the API documents no commission parameter. It's never zero ([what a backtest can support](what-a-backtest-can-support.md#commission-isnt-modeled)).
- **Five parameters aren't sent:** `max_pos_pct`, `rank_tolerance`, `carry_cost`, `long_weight`, and `short_weight`. Each is `not_sent`, with `unknown` provenance: Portfolio123's default applies, and it isn't documented.

The plan marks the same settings before you approve it: inferred defaults, settings not snapshotted, commission not modeled, and parameters not sent. [The flag codes](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#flag-codes) explain each flag.

## What isn't snapshotted

Some settings name an object in your Portfolio123 account rather than define it: the universe, always, and a ranking system named by `name` or `id`. Such an object can change in your account after the run, and Trial Folio doesn't retrieve its definition. So the run records it as an external reference that isn't snapshotted, flagged `not_snapshotted`, and the manifest's reproducibility is `incomplete` ([ranking forms](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-forms), [settings and differences](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#settings-and-differences)). If the object changes, the same configuration can give different results.

A formula ranking is recorded completely: the formula itself is in your configuration, the plan, the request, and `settings.csv`. But every configuration names its universe, which has no default ([D-19](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)), and the universe is never snapshotted. So a run's reproducibility reads `incomplete` whichever ranking form it uses. The manifest lists each external reference by its setting, so you can see which ones made it so.

## The configuration, byte for byte

Each run keeps your configuration file, byte for byte, as `configuration.yaml`, comments included. Source files are preserved exactly as they were, before anything is derived from them ([INV-04](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants)).

The plan, by contrast, holds no trace of how the file was written: comments, an omitted `data_vendor`, or `0.250` written for `0.25` don't change it ([plans and approval](plans-and-approval.md#the-plan-hash)). The copy keeps what the plan leaves out, and `settings.csv` gives each value as you wrote it, read from that copy.

An experiment keeps a copy for each plan you approve: `plans/<n>/configuration.yaml`, beside that plan's `plan.json` ([experiment output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-output)).

## The plan's package versions

A run's `plan.json` is the plan you approved. Besides the request and its settings, it records the version of Trial Folio that built it, and the versions of `p123api`, `requests`, and `urllib3` that send the request ([plan contents](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-contents)).

Those three packages are recorded because Trial Folio relies on exactly how they behave. The plan's retry policy describes the installed wrapper's behavior, and Trial Folio's transport adapter, which makes sure each request is sent at most once, relies on how `requests` and `urllib3` raise errors, follow redirects, and retry ([ADR 0006](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0006-observe-the-wrappers-http-exchanges.md), decision 7). The plan records all three, so your approval covers them, and each attempt's records hold them too.

The plan hash covers the versions. So after you upgrade Trial Folio, `p123api`, `requests`, or `urllib3`, the same configuration gives a new plan, which needs a new approval ([plan hashing](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-hashing)). For an experiment, that new plan is a revision of its current plan, even when the configuration hasn't changed. The revision records both versions of each package that changed, as a change of versions, not of the configuration, and like every revision it needs a reason ([experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)). The cases whose settings didn't change keep their attempts, as [how a revision keeps a case's identity](#how-a-revision-keeps-a-cases-identity) explains.

## Verified versions and `environment.unsupported`

Trial Folio plans only with versions of `p123api`, `requests`, and `urllib3` that a release has verified: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0. [Plan contents](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-contents) owns that list. The package pins each one exactly, so a fresh install gets them. Trial Folio also needs `requests` to write request bodies with Python's own `json` module, because its rules for decimals are verified only with it. `requests` uses `simplejson` instead whenever that's importable.

Any other installed version, or an importable `simplejson`, fails with `environment.unsupported`, exit code 3, before the plan is shown. Nothing is sent, and no output is created. The message names the verified versions, and says how to restore them. In a copy of the repository, `uv sync` restores the locked versions ([errors](../reference/errors.md)).

The exact pins have a cost: you can't take a new release of `requests` or `urllib3`, a security release included, on your own. Each one needs a Trial Folio release that verifies it ([ADR 0006](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0006-observe-the-wrappers-http-exchanges.md), consequences).

## The manifest and its hashes

A run's `manifest.json` records what ran and how: the command, the plan hash and how the plan was approved, the outcome and any error, its counts, its reproducibility, the parser versions, the license identifier and notice version, and a statement of what the run does and doesn't contain. It lists every file of the run, apart from its logs, with its path in the run, its size, its role, its schema version, and its `artifact_id`: the SHA-256 of the file's bytes ([artifact storage](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#artifact-storage)).

The manifest is written last, so a run without one is incomplete. After a Portfolio123 error, the run still has its report and manifest, which record the failure. After an interrupt, a storage failure, or an internal error, there's no manifest, so the run reads as incomplete. An experiment writes a report and a manifest for each session, in `sessions/<s>/`, and the newest supersedes the ones before it. A session without a manifest, because its command was interrupted, leaves the experiment reading as incomplete until the same command resumes it.

The hashes let Trial Folio check a saved run before it uses it. `trialfolio report`, and a review, read only the files the manifest lists, and check each one's size and `artifact_id`. The plan must compute to its own hash, too. A run that fails any check isn't a complete run: `input.not_a_run`, exit code 3. When you go on with an experiment, Trial Folio first checks its records against the latest manifest the same way. A file that's missing or changed, as after an incomplete copy, fails the check, rather than leaving a case that had an attempt looking as if it had none, to be sent again and left out of the budget ([running an experiment](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#running-an-experiment)).

Hashes detect changes. They don't prove that a provider's data is correct, and they don't make your files tamper-proof.

## How a revision keeps a case's identity

A case's `case_id` is the identity of its resolved settings: `case-` followed by the first 16 hex digits of the SHA-256 of their canonical form ([plan hashing](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-hashing)). It doesn't depend on the case's key or description, on the experiment's title or purpose, or on how the file is written. So a case has the same `case_id` as a screen run with the same settings.

That's what a revision relies on ([what a revision keeps](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)):

- **A case whose settings didn't change** keeps its `case_id`, and so its attempts, whatever its key now. A case that succeeded isn't sent again, even after a change of versions, because its request is what its settings send.
- **A case whose settings changed** is a new case, with a new `case_id`, even under the same key. The old case is retired: it and its attempts stay in the record, the plan display and the report list it, and the budget still counts its attempts.
- **A variant you remove** retires its case the same way. A later plan that includes the same settings again, under any key, includes that same case again, with its attempts.

Each plan's `experiment.json` is the experiment's research record as of that plan: its purpose, its planned and retired cases, its declared prior research, and every plan so far, with the reason for each revision and what it changed ([`experiment.json`](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experimentjson)). For the steps, see [revising an experiment](../how-to/revise-an-experiment.md).

## Why every attempt is recorded

Trial Folio records every attempt, including those that fail. Each one has its own folder, `cases/<case_id>/attempts/<attempt_id>/`, with its start record, `started.json`, written just before the request is sent; its attempt record, `attempt.json`, written once when it ends, whatever ended it; the request, without credentials; and Portfolio123's response, when one was saved. No record is ever overwritten ([execution outcomes and attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#execution-outcomes-and-attempts)).

There are three reasons:

- **All evidence is kept.** Trial Folio preserves everything it collects, failed and abandoned cases included ([INV-01](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants)), and accounts for every planned case, including skipped, failed, incomplete, and uncertain attempts ([INV-07](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants)). In an experiment's manifest, the planned cases always equal those that succeeded, failed, were skipped, are unknown, and haven't run yet.
- **The research history is complete.** An experiment's record of every case, attempt, and revision is the history that a later statistical assessment needs, and it can't be rebuilt afterwards ([METH-03](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing), [what the first three releases preserve](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#what-the-first-three-releases-preserve-without-evaluating)).
- **Charges are accounted for.** A failed request may still have been charged, so the budget counts every attempt that may have reached Portfolio123 ([credits and uncertain charges](credits-and-uncertain-charges.md)).

Logs aren't part of this record. They're diagnostics, kept in `logs/`, outside the manifest and its hashes, and they never hold credentials, configuration values, formulas, or results ([REQ-06](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements)).

Every file a run, a review, or an experiment holds is listed in the [outputs reference](../reference/outputs.md).

## Where it's specified

- [Provenance](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#provenance), [settings and differences](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#settings-and-differences), and [screen settings](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#screen-settings), in contracts.md.
- [Plan contents](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-contents) and [plan hashing](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-hashing), in contracts.md: the versions, the verified list, and `case_id`.
- [Artifact storage](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#artifact-storage) and [experiment output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-output), in contracts.md: the layouts and the manifests.
- [Experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions), in contracts.md: what a revision keeps.
- [ADR 0003](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0003-versioned-research-artifacts.md), versioned research artifacts, and [ADR 0006](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0006-observe-the-wrappers-http-exchanges.md), the exact versions.
- [The enduring invariants](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants), in spec.md.
