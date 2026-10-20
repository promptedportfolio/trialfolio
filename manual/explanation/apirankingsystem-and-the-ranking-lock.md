# `ApiRankingSystem` and the ranking lock

From release 0.4.0, a screen or an experiment whose ranking is a ranking system's definition, given in a file or by a ranking snapshot, writes each case's definition into a ranking system in your Portfolio123 account, `ApiRankingSystem`, just before the case's backtest. This page explains why, what that changes in your account, and what the lock that guards it can and can't exclude.

## Why Trial Folio writes a ranking system

A screen backtest through the API ranks by a formula, or by a ranking system saved in the account, by its name or its ID. Its request has no place for a ranking system's definition. So to rank a case by a definition, Trial Folio first writes the definition into a ranking system of the account, with Portfolio123's `rank_update`, then sends the backtest, ranked by that system's name.

Live calls verified that route before it was built: a backtest ranked by the system right after its `rank_update` used the definition just written, a changed weight changed the backtest's metrics, and writing the first definition again gave the first metrics back, so ranks aren't cached ([what R04-T01 verified](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md#what-r04-t01-verified)).

## Why `ApiRankingSystem`, and only it

`rank_update` without an ID writes `ApiRankingSystem`, a ranking system Portfolio123 keeps for the API, and creates it in your account the first time. Trial Folio writes only that system. It never gives `rank_update` an ID, never calls `rank_create`, and never writes a system you saved, or the one a snapshot reads: a snapshot only reads ([D-36](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). A test checks the body of every `rank_update` Trial Folio sends for it.

So the ranking systems you keep are never changed by Trial Folio, and `ApiRankingSystem` holds the definition the last case wrote. The plan says that the run overwrites it, before you approve. Three things follow:

- **Keep nothing of your own in `ApiRankingSystem`.** Every run with a ranking definition overwrites it.
- **Don't rank a screen by the name `ApiRankingSystem`.** A ranking by that name writes nothing, and ranks by whatever the system holds when its backtest runs, so Trial Folio records it as not snapshotted, as any ranking by name.
- **Rank by a definition or a snapshot instead,** which Trial Folio writes into the system itself, and records completely.

## Each case writes, then backtests

Each attempt of a case with a ranking definition sends two requests, in this order ([sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition)):

1. **`rank_update`,** with the case's whole definition, its ranking method, and the fixed currency, USD, and type, stock;
2. **the backtest,** ranked by `ApiRankingSystem`, sent only after the `rank_update` got a response Trial Folio could read, so it never ranks by whatever the system held before.

Nothing is sent between them. A resume and a repeat send both again, never a backtest alone: once a run ends, another process may have written the system since.

The two requests cost 6 credits at Portfolio123's documented costs: 1 for a `rank_update` and 5 for a backtest. The budget counts each as one provider request, so an experiment's budget is at least two requests a case. A case whose `rank_update` may have reached Portfolio123 is possibly charged, even when its backtest wasn't sent, so it waits for a [repeat](../how-to/repeat-a-case.md) rather than being sent again on its own ([credits and uncertain charges](credits-and-uncertain-charges.md)).

## What Portfolio123 stores

Each case's records hold the definition it sent, byte for byte: in the plan's request, which you approve, and in the attempt's `rank-update-request.json`. Trial Folio doesn't read the system back after writing it.

Portfolio123 stores a definition as equivalent XML, in its own serialization, rather than always byte for byte. The live check of release 0.4.0 found that it wrote each `StockFormula`'s attributes in an order of its own, and left out the final line feed. What it stores has the definition's elements, attributes, values, and text, and a run with the baseline's definition, after a variant's, gave back every metric of the baseline case ([changes after sign-off](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md#changes-after-sign-off)).

So a snapshot of `ApiRankingSystem`, taken after a run, holds the definition as Portfolio123 serialized it. A case is identified by its definition's bytes, so a plan ranked by that snapshot can give a different `case_id` from the run's, though its weights are the same.

## The ranking lock

Two Trial Folio processes that use one account at once could interleave their cases: one case's backtest could rank by the definition another case had just written. So a run that writes `ApiRankingSystem` holds a lock that no other Trial Folio process on the machine can hold at the same time ([the ranking lock](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-ranking-lock)).

- **Which runs take it:** a screen run ranked by a definition or a snapshot, and an experiment with a ranking definition when its run will send a case. A snapshot's run, a run ranked any other way, and a resume that sends nothing don't.
- **The file** is `trialfolio-ranking.lock`, in `/tmp` on Linux and macOS, and in the folder `%ProgramData%` names on Windows, usually `C:\ProgramData`. `TRIALFOLIO_LOCK_DIR` names another directory. Every user of the machine can open it, so it serializes every user's runs, and one lock serves every account. Trial Folio creates it when it's missing, and never writes to it: it stays empty, and it isn't evidence.
- **When it's taken:** after you approve the plan, and Trial Folio finds your credentials, before the run writes anything. The run holds it until it ends. The system releases it when the process ends, however it ends, so a run that's killed leaves no stale lock.
- **Held by another process:** the run fails with `experiment.locked`, exit code 4, before anything is sent or written. The message says that another Trial Folio process on this machine is writing `ApiRankingSystem`. Wait for it to end, and run the command again.
- **Can't be opened or locked,** such as in a directory that doesn't exist, or on a network file system that refuses the lock: the run fails with `storage.write_failed`, exit code 4, before anything is sent. The message names the file and the reason, and says that `TRIALFOLIO_LOCK_DIR` can name another directory.

## What the lock can't exclude

The lock excludes only Trial Folio processes that lock the same file. It can't exclude:

- **Portfolio123's website, or another machine,** writing or using `ApiRankingSystem` at the same time;
- **a process that sees another `/tmp`,** such as in a container, or one with another `TRIALFOLIO_LOCK_DIR`;
- **a process that locks a new file** after a program that cleans `/tmp` removed the one a run holds;
- **a screen ranked by the name `ApiRankingSystem`,** which takes no lock.

If one of those wrote the system between a case's `rank_update` and its backtest, that backtest would rank by another definition, and no record would show it. The plan display says what the lock can't exclude before you approve, and the report repeats it among its limitations. While a run with a ranking definition runs:

- don't edit `ApiRankingSystem` in Portfolio123's website, and don't run Trial Folio with the same account on another machine;
- give every Trial Folio process that doesn't see the same `/tmp`, such as one in a container, the same `TRIALFOLIO_LOCK_DIR`: a directory they all see, on a local file system.

## Where it's specified

- [Sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition) and [the ranking lock](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-ranking-lock), in contracts.md: the two requests, their records, and the lock.
- [Plans with a ranking definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-with-a-ranking-definition), in contracts.md: what the plan shows.
- [Release 0.4.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md): its scope, its exclusions, and what its live calls verified.
- [ADR 0001](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0001-python-and-portfolio123-integration.md), decision 5: why runs that share an object in the account are serialized.
