# Credits and uncertain charges

Each screen backtest Trial Folio sends uses Portfolio123 API credits: 5 a request, as Portfolio123 documents. This page explains how Trial Folio budgets them, why it treats a request that failed as possibly charged, and why it never sends a request again on its own.

## What a request costs

Portfolio123 documents a cost of 5 API credits for a screen backtest, on its [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen) page (checked 2026-10-01). A run sends one request, so it costs 5 credits. Each case of an experiment is a screen backtest, sent just as a screen configuration with its settings would be, so each case costs 5 credits too.

The plan's budget uses that documented cost, and records where it comes from and when it was checked. What Portfolio123 charged is a separate fact: when a response reports it, the attempt record keeps the `cost` Portfolio123 reported ([budget and retries](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#budget-and-retries)). A response can also say how many credits the account has left. The attempt record keeps that too, but no report, manifest, or JSON summary shows it: it's account information, and manifests may be shared.

Before it sends a request, Trial Folio authenticates with a call of its own, and again before a later request only when an earlier one got a 401 or 403, which drops the token. Portfolio123 doesn't document whether authentication costs credits. The two authentications that a live check could measure cost none, but that's an observation, not a documented price. So the budget's credits leave authentication out, and the budget bounds the number of authentication calls instead.

## The budget

Every plan has a budget, which the plan shows before you approve it ([plans and approval](plans-and-approval.md)).

- **A screen run's budget** is at most 1 provider request, 5 credits at the documented cost, and at most 1 authentication call. The request is sent at most once, so that's also the worst case.
- **An experiment's budget** is its `budget.provider_requests`: the most provider requests the experiment may send, across every run of it, repeats included. It must be at least the number of cases, so each case can be sent once, and anything more leaves room to repeat a case. The plan shows the credits, at 5 a request. When Trial Folio adds its default rebalance variant, that's a case like any other, and adds 5 credits. The experiment's authentication calls are bounded by the same number.

An experiment's budget counts requests, not credits, because Trial Folio counts its sends exactly, while credits depend on Portfolio123's price, which can change ([the experiment's budget](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-experiments-budget)).

A send counts against the budget when it may have reached Portfolio123, whatever its status or outcome. A send that provably never connected doesn't count. Before each send, Trial Folio checks that one more stays within the budget, and it never starts a send that would exceed it. In an experiment, the count covers every attempt: those of every case, retired cases included, under every plan, in every run. When the budget is spent, the case that would exceed it isn't started, and neither are the cases after it; they stay not yet run. A revision that raises the budget lets them run ([the budget across runs](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)).

## Why a failed request may be charged

Whether Portfolio123 charges for a request that fails is unknown: it isn't documented, and it hasn't been verified. So Trial Folio counts any request that may have reached Portfolio123 as possibly charged, whatever its outcome, and the plan says so.

!!! warning "May be charged"
    A request that reaches Portfolio123 may be charged even if it fails. Running a screen configuration again, into a new directory, or repeating an experiment's case, sends the request again, and may be charged again.

A request may have reached Portfolio123 unless its connection provably never opened: the name lookup failed, or the connection was refused, unreachable, or timed out before it opened. Trial Folio uses the test that `urllib3` itself uses to decide that a server didn't receive a request ([HTTP exchanges](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#http-exchanges)). Every other ending counts as possibly sent, such as a reset, a read timeout, a TLS failure, a response that broke off, or Ctrl-C while the request was being sent. So an unclear case counts as possibly sent.

A request that never connected fails with `provider.unavailable`. It wasn't sent, and isn't possibly charged.

## "Possibly charged" in attempt records

Each attempt's record, `attempt.json`, gives its outcome, `possibly_charged`, and the cost Portfolio123 reported, if any ([execution outcomes and attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#execution-outcomes-and-attempts)). The progress line in the terminal says the same, when the attempt ends: how it ended, and whether it may have been charged.

`possibly_charged` is true exactly when the attempt's outcome is `unknown`, or when its request may have reached Portfolio123. So:

- **A request that succeeded** is possibly charged: Portfolio123 received it.
- **A request Portfolio123 rejected,** such as with a 400 or a 409 (`provider.unsupported_capability`), a 402 (`provider.quota_exceeded`), or a 401 or 403 (`provider.auth_failed`), failed, and is possibly charged.
- **A failed authentication** is not possibly charged: the backtest request was never sent.
- **A request that never connected** is not possibly charged (`provider.unavailable`).

After a storage failure, the command ends with `storage.write_failed`, even if the request was already sent; the attempt record still says whether it may have been charged.

## `unknown` outcomes

An attempt is `unknown` when its request may have been sent, and charged, but no response was durably recorded. That happens after a read timeout or a reset, after a 5xx server error, after an interrupt while Trial Folio waits for Portfolio123, and when a 200 arrives but its response couldn't be saved. Outside an interrupt or a storage failure, a screen's command ends with `provider.outcome_unknown`, exit code 5. In an experiment, the case is `unknown`, the next case runs, and the command ends with `execution.partial`, exit code 6. After Ctrl-C, it ends with `command.interrupted`, exit code 130, and the message says whether a request may have been sent.

`unknown` always means that no response was saved. A response that arrived and was saved is `succeeded`, even when it then fails validation.

A process that's killed, for example by a power loss, can't record anything. Trial Folio writes an attempt's start record durably just before it sends the request, so a start record without an attempt record shows that a request may have gone out. It counts as possibly charged, and as one provider request. When an experiment resumes, Trial Folio records such an attempt as `succeeded` if its response was saved, and `unknown` otherwise ([uncertain completion](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#uncertain-completion)).

## Why Trial Folio never resends a request on its own

Left to itself, the `p123api` wrapper would send a request more than once. It retries a failed connection or a 5xx, up to 5 attempts in all by default, and after a 401 or 403 it authenticates again and resends the request. So one call to it could send a charged request more than once, or end with an unknown outcome ([ADR 0001's verification notes](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0001-python-and-portfolio123-integration.md#verification-notes)).

Trial Folio prevents that. It sets the wrapper to one HTTP attempt per call, and its own transport adapter refuses any second exchange in a call before it connects, such as the wrapper's resend after a 401 or 403, or a redirect ([ADR 0006](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0006-observe-the-wrappers-http-exchanges.md)). Its retry policy is 0 automatic retries. So each request is sent at most once for each approval, and can use at most its documented cost. One consequence: if Portfolio123 refuses the request's authorization, the attempt fails, instead of authenticating again.

An `unknown` attempt in particular is never retried automatically, because its request may already have been charged, or may have changed something at Portfolio123 ([uncertain completion](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#uncertain-completion)). Sending a request again is always your decision:

- **For a screen,** running the command again, into a new directory, is a new attempt of the same case, and may be charged again. Portfolio123's data and engine change, so its results may differ, and it never replaces the earlier run ([reproducibility](reproducibility.md)).
- **In an experiment,** only a repeat sends such a request again, below.

## What a resume sends

When you run an experiment's command again, it resumes the experiment, and treats each case by its state ([the cases that are due](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#running-an-experiment)):

- **Complete:** one of its attempts succeeded, so its response was saved. It's never sent again.
- **Due:** it has no attempt, or each failed before its request could reach Portfolio123, as after a failed authentication. A resume sends it.
- **Awaiting a repeat:** its request may have reached Portfolio123, and may have been charged, but none of its attempts succeeded. It's `unknown`, or `failed` after Portfolio123 rejected it. A resume never sends it on its own.

A case Portfolio123 rejected waits for a repeat just as an `unknown` one does, because whether Portfolio123 charges a failed request is unverified. So a resume sends only requests that can't already have been charged.

Two failures stop an experiment's run before its later cases: Trial Folio's own authentication call failing, as with wrong credentials, and `provider.quota_exceeded`. Every later case would end the same way, and each would first use one of the experiment's authentication calls, so wrong credentials could use them all, and only a revision with a larger budget could run the experiment again ([D-32](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). The run records the case's attempt, starts no later case, and ends with `execution.partial`, exit code 6. Once you've fixed the cause, running the same command again runs the cases it didn't start. A request that got `provider.quota_exceeded` may have been charged, so that case waits for a repeat.

To resume after an interrupt, see [recovering from an interrupt](../how-to/recover-from-an-interrupt.md).

## Why a repeat needs a confirmation

A case awaiting a repeat is sent again only when `--repeat` names it, and you confirm that its request may be charged again ([repeating a case](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#repeating-a-case)). You confirm by typing `repeat` in a terminal, or by giving the attempt's ID, as in `--repeat holdings-50:<attempt-id>`. The attempt ID names the attempt whose possible charge you acknowledge, as `--approve` names the plan you approve. Without `--repeat`, such a case could never be sent again: a revision keeps a case whose settings didn't change, with its attempts.

A repeat is a new attempt of the same case, with the same `case_id`. It may be charged again, and it counts against the experiment's budget. When the budget can't cover it, it doesn't start. A run that starts nothing for that reason needs no credentials, and a revision that raises the budget lets the same option repeat it.

One confirmation allows one repeat. Once the repeat may have reached Portfolio123, running the same command again, as after an interruption, doesn't repeat the case on the same confirmation. If that repeat didn't succeed either, repeating the case again needs a new confirmation, which names the repeat's own attempt. A key with a flag that acknowledged the charge would have repeated the case each time the same command ran ([open questions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#open-questions)).

A repeat isn't a new case, candidate, or hypothesis: it's another attempt at the same request. The experiment's manifest counts the repeats apart from the other attempts, and keeps provider operations apart from the cases ([METH-03.2](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)). For the steps, see [repeating a case](../how-to/repeat-a-case.md).

## Checking your API credits

Trial Folio can't tell whether Portfolio123 charged a request that failed, and an `unknown` request may have gone through. Before you run a command again, or repeat a case, you can check your API credits on Portfolio123's website. The messages for an `unknown` outcome, for an interrupt, and for `provider.quota_exceeded` suggest it.

`provider.quota_exceeded` means Portfolio123 refused the request because of the account's quota or credits. The request may have been charged. Check your API credits before you run the command again. In an experiment, once the account has credits again, the same command resumes the experiment, and runs the cases not started.

The error codes, and what to do about each, are in the [errors reference](../reference/errors.md).

## Where it's specified

- [Budget and retries](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#budget-and-retries) and [HTTP exchanges](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#http-exchanges), in contracts.md: the documented cost, what counts, possibly charged, and the retry policy.
- [Execution outcomes and attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#execution-outcomes-and-attempts) and [uncertain completion](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#uncertain-completion), in contracts.md.
- [Experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions), [running an experiment](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#running-an-experiment), and [repeating a case](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#repeating-a-case), in contracts.md: the budget across runs, the cases that are due, and the repeat.
- [ADR 0006](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0006-observe-the-wrappers-http-exchanges.md): why each request is sent at most once.
- [Release 0.1.0's failure behavior](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior), which maps each failure to an outcome and an error code.
