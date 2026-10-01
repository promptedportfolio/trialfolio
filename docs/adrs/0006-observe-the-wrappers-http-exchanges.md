# ADR 0006: Observe the wrapper's HTTP exchanges

**Status:** Proposed. Adopted when 0.1.0 is implemented with this design, after R01-T09 verifies it against the installed wrapper. Extends decision 6 of [ADR 0001](0001-python-and-portfolio123-integration.md), and answers its follow-up condition on wrapper retries.
**Date:** 2026-10-01

## Context

[ADR 0001](0001-python-and-portfolio123-integration.md), decision 6, makes each HTTP attempt visible. Whether a screen backtest request could have reached Portfolio123 decides whether an attempt is possibly charged, and whether running it again could charge twice. In `p123api` 3.1.0, the wrapper hides that in three ways (verified observations from its source, with `requests` 2.34 and `urllib3` 2.8):

- **A resend after 401 or 403.** The wrapper re-authenticates and resends the request once. No setting disables it.
- **A 5xx looks like a failed connection.** Allowed one attempt, the wrapper discards a 5xx response and raises the same "Cannot connect to API" exception as a failed connection.
- **The exceptions don't say what was sent.** A refused connection, a failed name lookup, and a connection reset all raise the same `requests` exception type. A read timeout while reading the body carries no request. A body that breaks off, and a 200 whose body isn't JSON, reach the caller as unwrapped `requests` errors.

The first draft of the plan specification inferred which request failed from the wrapper's exceptions: the request path, the cause's type, and special cases on top. Its review found failures that no rule covered, and rules that contradicted each other.

## Decision

1. **Record each exchange at the transport layer.** Trial Folio mounts its own transport adapter, a subclass of `requests`' `HTTPAdapter`, on the wrapper's HTTP session. Every request the wrapper makes passes through it: Trial Folio's own authentication call, the backtest request, and the wrapper's re-authentication and resend.
2. **What it records.** For each exchange, in memory and in order: the method and path, and the result, which is one of these:
   - `response`, with the HTTP status
   - `not_connected`
   - `interrupted`

   The adapter reads the response body before returning, so a body that breaks off is recorded too. It records nothing else: no headers, bodies, tokens, or exception objects. It changes no request or response, and passes every error on unchanged, so the wrapper behaves as it would without it.
3. **Not connected means provably not sent.** An exchange is `not_connected` only when the connection was never established: the underlying `urllib3` error is a `ConnectTimeoutError`, which covers a failed name lookup, a refused or unreachable connection, and a connect timeout. `urllib3` uses the same test to decide that a request is safe to retry, because the server didn't receive it. Every other error is `interrupted`, so an unclear case counts as possibly sent.
4. **Classification reads the exchanges.** Trial Folio classifies an attempt's outcome from its exchanges, never from the wrapper's exception. From the exception it takes only a sanitized message (ADR 0001, decision 7). The attempt record keeps the exchanges.
5. **Exact versions.** The adapter relies on the wrapper's session, a private attribute (`Client._session` in 3.1.0), and on how `requests` 2 and `urllib3` 2 raise errors. So the package pins `p123api` exactly, and constrains `requests` and `urllib3` to major version 2. Each attempt record holds the installed version of all three. A new wrapper version is verified before Trial Folio accepts it.

[contracts.md, HTTP exchanges](../contracts.md#http-exchanges) specifies the record, and [0.1.0's failure behavior](../releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) the classification.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Infer the failed request from the wrapper's exception (the first draft) | It depends on the same library internals, leaves the resend and a 5xx unobservable, and needs a rule for every exception shape. Its review found shapes it missed. |
| Call the HTTP API directly, without `p123api` | It gives full control, but duplicates the authentication and endpoint handling that ADR 0001 and [ADR 0005](0005-build-on-the-portfolio123-api-only.md) chose not to duplicate. Reconsider it if a later wrapper version leaves no session to mount an adapter on. |
| A response hook on the session | A hook sees only responses, not connection errors or bodies that break off. |
| Patch or subclass the wrapper's client | It changes the wrapper's behavior, and couples Trial Folio to more of its internals than one session attribute. |

## Consequences

- **The resend is recorded.** It still can't be prevented, so the worst-case budget stays at two backtest requests.
- **Failures are told apart.** A 5xx is told apart from a failed connection, and a failure of the wrapper's re-authentication from a failure of the backtest request.
- **Possibly charged is a recorded fact.** It follows from which exchanges connected, not from an inference about the exception.
- **One private attribute.** Upgrading `p123api` requires re-verifying the adapter, which ADR 0001's follow-up conditions already require for any wrapper behavior Trial Folio relies on.

## Follow-up conditions

- R01-T09 verifies the adapter against the installed `p123api`, `requests`, and `urllib3`: every exchange passes through it, and each failure kind gets its documented result.
- If a wrapper version stops exposing a session Trial Folio can mount an adapter on, write a new ADR that considers direct HTTP calls.
