"""The Portfolio123 provider client: `ScreenBacktestClient`, over `p123api`, and the transport
adapter that records each HTTP exchange the wrapper makes (docs/contracts.md, HTTP exchanges and
credentials; ADR 0001, decisions 6 and 7; ADR 0006).

The package's modules, each importing only those before it:

- `credentials`: `Credentials`, the API ID and key, which nothing serializes or logs.
- `adapter`: `ExchangeRecordingAdapter`, which records each exchange, and allows one in each call
  to the wrapper. It logs the exchanges as `trialfolio.provider`, as no other module here does.
- `failures`: `ProviderError`, and each call's table of messages, from which a failed call's
  error is classified, with Portfolio123's own text sanitized.
- `client`: `ScreenBacktestClient`, and `P123ScreenBacktestClient`, which configures the wrapper,
  and makes each call through the adapter.

Every name the rest of Trial Folio uses is imported from `trialfolio.provider`, as before it was a
package.

R01-T09 verified the client and the adapter against `p123api` 3.1.0, `requests` 2.34.2, and
`urllib3` 2.8.0, from their source and with tests in tests/provider/ over a local server and
socket faults:

- `p123api`'s `req_with_retry` catches only `requests.ConnectionError`, discards a 5xx, and raises
  `ClientException("Cannot connect to API")` once its attempts are used up.
  `_req_with_auth_fallback` calls `auth()` itself when the session has no `Authorization` header,
  and after a 401 or 403 deletes the header and calls `auth()` again, which clears the session's
  headers before sending `POST /auth`.
- `requests`' `Session.send` follows a redirect by calling `send` on the session again, which
  reaches the adapter mounted for the new URL's scheme.
- `HTTPAdapter.send` raises the `requests` error with the `urllib3` error as its first argument.
  A `MaxRetryError` arrives there only after `urllib3`'s `Retry.increment`, which, with
  `read=False`, re-raises a read error or a reset unwrapped instead.
"""

from trialfolio.provider.adapter import CallKind, ExchangeRecordingAdapter, ExchangeRefused
from trialfolio.provider.client import (
    REQUEST_TIMEOUT_SECONDS,
    DecodedResponse,
    P123ScreenBacktestClient,
    ScreenBacktestClient,
    ScreenBacktestResponse,
    UndecodedResponse,
)
from trialfolio.provider.credentials import Credentials
from trialfolio.provider.failures import ProviderError, provider_message_of

__all__ = [
    "REQUEST_TIMEOUT_SECONDS",
    "CallKind",
    "Credentials",
    "DecodedResponse",
    "ExchangeRecordingAdapter",
    "ExchangeRefused",
    "P123ScreenBacktestClient",
    "ProviderError",
    "ScreenBacktestClient",
    "ScreenBacktestResponse",
    "UndecodedResponse",
    "provider_message_of",
]
