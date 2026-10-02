# ADR 0006: Observe the wrapper's HTTP exchanges

**Status:** Proposed. Adopted when 0.1.0 is implemented with this design, after R01-T09 verifies it against the installed wrapper. Extends decision 6 of [ADR 0001](0001-python-and-portfolio123-integration.md), and answers its follow-up condition on wrapper retries.
**Date:** 2026-10-01

## Context

[ADR 0001](0001-python-and-portfolio123-integration.md), decision 6, makes each HTTP attempt visible. Whether a screen backtest request could have reached Portfolio123 decides whether an attempt is possibly charged, and whether running it again could charge twice. In `p123api` 3.1.0, the wrapper and `requests` hide that, or send more than one request, in four ways (verified observations from their source, with `requests` 2.34 and `urllib3` 2.8):

- **A resend after 401 or 403.** The wrapper re-authenticates and resends the request once. No setting disables it.
- **Redirects are followed.** `requests` follows up to 30 redirects by default: a 301, 302, 303, 307, or 308 with a `Location` header. On a 307 or 308 it sends the same method and body again, to whatever host the redirect names.
- **A 5xx looks like a failed connection.** Allowed one attempt, the wrapper discards a 5xx response and raises the same "Cannot connect to API" exception as a failed connection.
- **The exceptions don't say what was sent.** A refused connection, a failed name lookup, and a connection reset all raise the same `requests` exception type. While the body is read, a read timeout or a TLS error becomes a `requests.ConnectionError` that carries no request, and the wrapper turns it into the same "Cannot connect to API". A body that breaks off becomes a `ChunkedEncodingError`, and a 200 whose body isn't JSON a `requests` `JSONDecodeError`, and both reach the caller unwrapped.

The first draft of the plan specification inferred which request failed from the wrapper's exceptions: the request path, the cause's type, and special cases on top. Its review found failures that no rule covered, and rules that contradicted each other.

## Decision

1. **Record each exchange at the transport layer.** Trial Folio mounts its own transport adapter, a subclass of `requests`' `HTTPAdapter`, on the wrapper's HTTP session, for both `https://` and `http://`. Every request the wrapper makes passes through it. Trial Folio also sets the session's `trust_env` to `False`, so no proxy, certificate-bundle, or `.netrc` setting in the environment applies ([contracts.md, credentials](../contracts.md#credentials)).
2. **What it records.** For each exchange, in memory and in order: the method and path, and the result, which is one of these:
   - `response`, with the HTTP status
   - `not_connected`
   - `interrupted`

   The adapter records each exchange before sending it, reads the body itself, and records nothing but the method, path, result, and status. The one exception is the body of a 200 on the request's exchange, which it holds so that Trial Folio can save it undecoded if the wrapper can't decode it. It changes no request or response, and passes every error on unchanged.
3. **Not connected means provably not sent.** An exchange is `not_connected` only when `urllib3`'s own test, the one its `Retry` uses to decide that the server didn't receive a request, says so. Every other ending without a complete response is `interrupted`, so an unclear case counts as possibly sent.
4. **Classification reads the exchanges,** and whether the call returned a decoded response, never the wrapper's exception object beyond its type and a sanitized message (ADR 0001, decision 7).
5. **One exchange per call.** During each call to the wrapper, Trial Folio's own authentication call or a request's call, the adapter allows exactly one exchange, and refuses any further one before connecting, whatever its path, with an error of Trial Folio's own type that ends the call. So each request is sent at most once, without depending on how a second send would come about. In 3.1.0 that refuses the wrapper's re-authentication and resend after a 401 or 403, and any redirect `requests` would follow. The adapter keeps `requests`' default `urllib3` retry setting, so `urllib3` never resends within one exchange either.
6. **Authenticate only when needed.** Trial Folio authenticates with its own call before the first request, and again only before a request that follows a 401 or 403, after which the wrapper has dropped its token. The plan's budget states the most authentication calls, because Portfolio123 doesn't document their cost. The two that R01-T05's live checks could measure cost no credits.
7. **Exact versions.** The adapter relies on the wrapper's session, a private attribute (`Client._session` in 3.1.0), on how the wrapper reacts to an error during a call, and on how `requests` and `urllib3` raise errors, send a redirect through the session, and retry. So all three are treated alike. The package pins each one exactly, to the versions [contracts.md, plan contents](../contracts.md#plan-contents) lists. Trial Folio refuses to plan with any other installed version, the plan records all three versions so approval binds them, and each attempt record holds them. A new version of any of them is verified before Trial Folio accepts it.

[contracts.md, HTTP exchanges](../contracts.md#http-exchanges) owns the exact rules: the record, the `not_connected` test, possibly charged, the one-exchange rule, and when Trial Folio authenticates. [0.1.0's failure behavior](../releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) maps each situation to an outcome and an error code.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Infer the failed request from the wrapper's exception (the first draft) | It depends on the same library internals, leaves the resend and a 5xx unobservable, and needs a rule for every exception shape. Its review found shapes it missed. |
| Let the wrapper resend after a 401 or 403, and record both sends (the second draft) | It allows two charged sends for one approval, and needs failure rules for every way the re-authentication and the resend can end. A resend after Trial Folio's own fresh authentication is unlikely to succeed. |
| Refuse each known resend path separately (the third draft): `POST /auth` during a request's call, and `max_redirects` set to 0 | Each rule depends on one way the wrapper or `requests` sends again. A path a later version adds, such as a retry on 429, would slip through. |
| Authenticate before every request | It doubles the provider calls in a run with several requests, and authentication's cost isn't documented. |
| Call the HTTP API directly, without `p123api` | It gives full control, but duplicates the authentication and endpoint handling that ADR 0001 and [ADR 0005](0005-build-on-the-portfolio123-api-only.md) chose not to duplicate. Reconsider it if a later wrapper version leaves no session to mount an adapter on. |
| A response hook on the session | A hook sees only responses, not connection errors or bodies that break off. |
| Patch or subclass the wrapper's client | It changes the wrapper's behavior, and couples Trial Folio to more of its internals than one session attribute. |

## Consequences

- **One send per approval.** The request is sent at most once, so it can use at most its documented cost, 5 credits for a screen backtest. Authentication isn't included, because its cost isn't documented; the budget bounds the number of authentication calls instead.
- **No retry on a 401 or 403.** If Portfolio123 refuses the request's authorization, the attempt fails instead of re-authenticating. Running the command again is a new attempt. In a run with several requests, a token that expires costs one failed attempt, and Trial Folio authenticates again before the next request.
- **Failures are told apart.** A 5xx is told apart from a failed connection, and an authentication failure from a failure of the request.
- **Possibly charged is a recorded fact.** It follows from which exchanges connected, not from an inference about the exception.
- **One private attribute.** Upgrading `p123api` requires re-verifying the adapter, which ADR 0001's follow-up conditions already require for any wrapper behavior Trial Folio relies on.
- **Exact pins have a cost.** A user can't take a security release of `requests` or `urllib3` on their own: the installed version would no longer be a verified one. Each such release needs a Trial Folio patch release that verifies it and moves the pin.

## Follow-up conditions

- R01-T09 verifies the adapter against the installed `p123api`, `requests`, and `urllib3`: every exchange passes through it, each failure kind gets its documented result, a second exchange in a call is refused before connecting, and `urllib3` retries stay off.
- If a wrapper version stops exposing a session Trial Folio can mount an adapter on, write a new ADR that considers direct HTTP calls.
