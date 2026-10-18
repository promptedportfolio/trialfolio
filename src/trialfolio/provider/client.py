"""The provider client: `ScreenBacktestClient`, the protocol, and `P123ScreenBacktestClient`, its
implementation over `p123api` (docs/contracts.md, protocols, HTTP exchanges, and credentials;
ADR 0001, decisions 6 and 7; ADR 0006).

`P123ScreenBacktestClient` drives the wrapper in two calls: Trial Folio's own authentication call,
and the request's call. The caller writes the start record between them. From 0.4.0, a case whose
ranking is a definition makes a request's call before its backtest's too: the `rank_update`, which
writes the definition into `ApiRankingSystem` (sending a definition). A ranking snapshot's request
is a `rank_get`, which reads the system its configuration names: the wrapper's `RankInfoResult`
keeps only the fields it knows, so the client decodes the 200's body its adapter holds instead,
with the standard library's `json`, `cost` and `quotaRemaining` included (`p123api-rank-get`
version 1). The client configures the wrapper's session, a private attribute (`Client._session` in
3.1.0):

- **One HTTP attempt per call.** `set_max_request_retries(1)`, for authentication and the request.
- **The timeout.** `set_timeout(300)`, the wrapper's own default, set explicitly. Tests may pass a
  shorter one; the installed command never does.
- **No environment settings.** `trust_env` is `False`, so no proxy, certificate-bundle, or
  `.netrc` setting in the environment applies.
- **The adapter.** `ExchangeRecordingAdapter` replaces the session's adapters, for both
  `https://` and `http://`. It records each exchange before sending it, reads the body itself,
  and refuses any second exchange in a call before connecting, with `ExchangeRefused`. The
  wrapper catches only `requests.ConnectionError`, so that ends the call. It keeps `requests`'
  default `urllib3` retry setting, `Retry(0, read=False)`.

A failed call raises `ProviderError`, classified from the call's exchange, whether the adapter
refused a second one, and the wrapper exception's type and message, never anything else on it
(`trialfolio.provider.failures`). The error is raised outside the handler, so it carries no
reference to the wrapper's exception, whose response holds the bearer token and, for
authentication, the API key.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Final, Protocol, Self, cast

import p123api  # pyright: ignore[reportMissingTypeStubs]: the package ships no types
import requests

from trialfolio.contracts.attempt import Exchange
from trialfolio.provider.adapter import ExchangeRecordingAdapter
from trialfolio.provider.credentials import Credentials
from trialfolio.provider.failures import (
    AUTHENTICATION,
    BACKTEST,
    RANK_GET,
    RANK_UPDATE,
    SNAPSHOT_AUTHENTICATION,
    CallMessages,
    ProviderError,
)

REQUEST_TIMEOUT_SECONDS: Final = 300
"""The request's timeout, set with the wrapper's `set_timeout` (HTTP exchanges, timeouts)."""


@dataclass(frozen=True)
class DecodedResponse:
    """The JSON value the wrapper decoded from the request's 200, saved as `response.json`."""

    payload: object


@dataclass(frozen=True)
class UndecodedResponse:
    """The body of a 200 the wrapper couldn't decode, saved as `response.raw`, labeled undecoded
    (HTTP exchanges)."""

    body: bytes = field(repr=False)


type ScreenBacktestResponse = DecodedResponse | UndecodedResponse


class ScreenBacktestClient(Protocol):
    """Executes the one supported screen-backtest request, and, from 0.4.0, the `rank_update`
    that writes a case's ranking definition before it, and a ranking snapshot's `rank_get`, and
    returns the captured provider evidence (docs/contracts.md, protocols).

    The caller authenticates with `authenticate`, writes the start record, and only then calls
    `screen_backtest`, `rank_update`, or `rank_get`, at most once for each approved send.
    `exchanges` gives every exchange so far, in order, at any time, including after an interrupt.
    No call retries anything.
    """

    @property
    def authenticated(self) -> bool:
        """Whether the client holds a token. It doesn't before authenticating, or after
        authentication failed or a request got a 401 or 403."""
        ...

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        """Every exchange so far, in order. One still without a result reads as `interrupted`."""
        ...

    def authenticate(self) -> None:
        """Makes Trial Folio's own authentication call: exactly one exchange, `POST /auth`.

        Raises `ProviderError` with `provider.auth_failed`, `provider.request_rejected`,
        `provider.unavailable`, or `internal.unexpected`. A user interrupt propagates unchanged.
        """
        ...

    def screen_backtest(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        """Sends `POST /screen/backtest` with `params` as its JSON body, at most once.

        Returns the decoded response, or the undecoded body of a 200 the wrapper couldn't decode.
        Raises `ProviderError` with the code the request's exchange gives it, and `RuntimeError`,
        before sending anything, unless the client is `authenticated`. A user interrupt
        propagates unchanged.
        """
        ...

    def rank_update(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        """Sends `POST /rank` with `params` as its JSON body, at most once: `p123api`'s
        `rank_update`, which writes a case's ranking definition into `ApiRankingSystem`, since
        `params` carries no `id` (sending a definition).

        Returns and raises as `screen_backtest` does, with the code its exchange gives it.
        """
        ...

    def rank_get(self, name: str) -> ScreenBacktestResponse:
        """Sends `GET /rank` with `name` as its query, at most once: `p123api`'s `rank_get`, which
        reads the ranking system saved in the account by that name, and writes nothing (ranking
        snapshot output).

        Returns the 200's body, decoded with the standard library's `json`, since the wrapper's
        result leaves out `cost` and `quotaRemaining`, or undecoded when the wrapper raised after
        the 200, as for a ranking method it doesn't know. Raises as `screen_backtest` does, with
        the code its exchange gives it.
        """
        ...

    def close(self) -> None:
        """Closes the client's connections."""
        ...


class _Wrapper(Protocol):
    """The part of `p123api.Client` 3.1.0 Trial Folio uses, typed: the package ships no types."""

    _session: requests.Session

    def set_max_request_retries(self, retries: int) -> None: ...
    def set_timeout(self, timeout: int) -> None: ...
    def get_token(self) -> str | None: ...
    def auth(self) -> None: ...
    def screen_backtest(self, params: dict[str, object], to_pandas: bool = False) -> object: ...
    def rank_update(self, params: dict[str, object]) -> object: ...
    def rank_get(self, *, name: str) -> object: ...
    def close(self) -> None: ...


class P123ScreenBacktestClient:
    """`ScreenBacktestClient` over `p123api`'s `Client`, configured as the module says."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        endpoint: str | None = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        snapshot: bool = False,
    ) -> None:
        """`endpoint` and `timeout` are for tests only (docs/contracts.md, credentials): without
        `endpoint`, the wrapper's default, Portfolio123's API, applies. `snapshot` is for a
        ranking snapshot's client, whose authentication's messages say that its `rank_get`, not
        a backtest, wasn't sent."""
        if endpoint is None:
            client = p123api.Client(api_id=credentials.api_id, api_key=credentials.api_key)
        else:
            client = p123api.Client(
                api_id=credentials.api_id, api_key=credentials.api_key, endpoint=endpoint
            )
        self._wrapper = cast(_Wrapper, client)
        self._secrets = (credentials.api_id, credentials.api_key)
        self._authentication = SNAPSHOT_AUTHENTICATION if snapshot else AUTHENTICATION
        self._wrapper.set_max_request_retries(1)
        self._wrapper.set_timeout(timeout)
        # The private attribute ADR 0006 relies on.
        self._session = self._wrapper._session  # pyright: ignore[reportPrivateUsage]
        self._session.trust_env = False
        self._adapter = ExchangeRecordingAdapter()
        self._session.adapters.clear()
        self._session.mount("https://", self._adapter)
        self._session.mount("http://", self._adapter)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def authenticated(self) -> bool:
        return "Authorization" in self._session.headers

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        return self._adapter.exchanges

    def authenticate(self) -> None:
        with self._adapter.call("authentication") as call:
            try:
                self._wrapper.auth()
            # Every failure is classified, from the exchange rather than the exception.
            except Exception as error:  # noqa: BLE001
                # Portfolio123's own text is redacted of the credentials and the token.
                secrets = (*self._secrets, self._wrapper.get_token())
                failure = self._authentication.failure(call.exchange, call.refused, error, secrets)
            else:
                return
        raise failure

    def screen_backtest(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        sent = self._request(
            lambda: self._wrapper.screen_backtest(dict(params), to_pandas=False), BACKTEST
        )
        # Raised here, outside the handler, so it carries no reference to the wrapper's
        # exception.
        if isinstance(sent, ProviderError):
            raise sent
        return sent

    def rank_update(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        sent = self._request(lambda: self._wrapper.rank_update(dict(params)), RANK_UPDATE)
        if isinstance(sent, ProviderError):
            raise sent
        return sent

    def rank_get(self, name: str) -> ScreenBacktestResponse:
        sent = self._request(lambda: self._wrapper.rank_get(name=name), RANK_GET, decode_body=True)
        if isinstance(sent, ProviderError):
            raise sent
        return sent

    def _request(
        self, send: Callable[[], object], messages: CallMessages, *, decode_body: bool = False
    ) -> ScreenBacktestResponse | ProviderError:
        """Makes the request's call, `send`, and returns its decoded response, or the undecoded
        body of a 200, or its failure, classified from its exchange, for the caller to raise.
        With `decode_body`, the decoded response is the 200's body its adapter holds, decoded
        with the standard library's `json`, rather than what the wrapper returned: undecoded when
        `json` can't decode it."""
        if not self.authenticated:
            # Otherwise the wrapper would authenticate inside the request's call, and the adapter
            # would refuse the request as its second exchange.
            raise RuntimeError("Trial Folio authenticates with its own call before a request")
        with self._adapter.call("request") as call:
            try:
                payload = send()
            except Exception as error:  # noqa: BLE001 (classified, as above)
                body = call.body
                if body is not None:
                    # Whatever the wrapper raised after the 200, it didn't return a decoded
                    # response, so the body is kept undecoded (HTTP exchanges).
                    return UndecodedResponse(body)
                secrets = (*self._secrets, self._wrapper.get_token())
                failure = messages.failure(call.exchange, call.refused, error, secrets)
            else:
                if decode_body:
                    return _decoded_body(call.body)
                return DecodedResponse(payload)
        return failure

    def close(self) -> None:
        self._wrapper.close()


def _decoded_body(body: bytes | None) -> ScreenBacktestResponse:
    """A 200's body, which the adapter holds, decoded with the standard library's `json`, as the
    wrapper decoded it already; or undecoded, when `json` can't decode it."""
    if body is None:  # The adapter holds every 200's body on the request's exchange.
        raise RuntimeError("a request's 200 has its body")
    try:
        return DecodedResponse(json.loads(body))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return UndecodedResponse(body)
