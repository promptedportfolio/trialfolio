"""The Portfolio123 provider client: `ScreenBacktestClient`, over `p123api`, and the transport
adapter that records each HTTP exchange the wrapper makes (docs/contracts.md, HTTP exchanges and
credentials; ADR 0001, decisions 6 and 7; ADR 0006).

`P123ScreenBacktestClient` drives the wrapper in two calls: Trial Folio's own authentication call,
and the request's call. The caller writes the start record between them. The client configures
the wrapper's session, a private attribute (`Client._session` in 3.1.0):

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
refused a second one, and the wrapper exception's type and message, never anything else on it.
The error is raised outside the handler, so it carries no reference to the wrapper's exception,
whose response holds the bearer token and, for authentication, the API key.

R01-T09 verified this against `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0, from their
source and with tests in tests/provider/ over a local server and socket faults:

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

import logging
import re
import time
import unicodedata
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import TracebackType
from typing import Final, Literal, Protocol, Self, cast
from urllib.parse import urlsplit

import p123api  # pyright: ignore[reportMissingTypeStubs]: the package ships no types
import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, ProxyError

from trialfolio.contracts.attempt import Exchange
from trialfolio.errors import ErrorCode, TrialFolioError

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS: Final = 300
"""The request's timeout, set with the wrapper's `set_timeout` (HTTP exchanges, timeouts)."""

_REDIRECTS: Final = frozenset({301, 302, 303, 307, 308})
"""The statuses `requests` follows when the response has a `Location` header."""

_REAUTHENTICATES: Final = frozenset({401, 403})
"""The statuses after which the wrapper drops its token, re-authenticates, and resends."""

_MAX_PROVIDER_MESSAGE: Final = 300
"""The most characters of Portfolio123's own message an error keeps."""

type CallKind = Literal["authentication", "request"]


class Credentials:
    """A Portfolio123 API ID and API key (docs/contracts.md, credentials; REQ-09, INV-11).

    A credential object is never serialized, hashed, logged, or written to an artifact. Its repr
    shows neither value, and pickling or copying it raises `TypeError`.
    """

    __slots__ = ("_api_id", "_api_key")

    def __init__(self, api_id: str, api_key: str) -> None:
        """Raises `TrialFolioError` with `provider.auth_failed` if either value is blank."""
        if not api_id.strip() or not api_key.strip():
            raise TrialFolioError(
                "provider.auth_failed",
                "Portfolio123 credentials are missing: Trial Folio needs both an API ID and an "
                "API key. Portfolio123's website lists them under DataMiner & API.",
            )
        self._api_id = api_id
        self._api_key = api_key

    @property
    def api_id(self) -> str:
        return self._api_id

    @property
    def api_key(self) -> str:
        return self._api_key

    def __repr__(self) -> str:
        return "Credentials(api_id=<redacted>, api_key=<redacted>)"

    def __reduce__(self) -> tuple[object, ...]:
        raise TypeError("credentials are never serialized or copied")


class ProviderError(TrialFolioError):
    """A provider call that failed, with the code 0.1.0's failure table gives it
    (docs/releases/0.1.0-api-execution.md, failure behavior).

    `message` is for the terminal and the attempt record. It ends with Portfolio123's own message,
    sanitized, when the failure table calls for it and the wrapper's message carries one. That
    text can repeat configuration values, so `log_message`, which is also the error's `str()`,
    leaves it out (docs/contracts.md, errors and credentials).
    """

    def __init__(self, code: ErrorCode, message: str, provider_message: str | None = None) -> None:
        full = message
        if provider_message is not None:
            full = f'{message} Portfolio123\'s message: "{provider_message}"'
        super().__init__(code, full, message)
        self.provider_message = provider_message

    def __reduce__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
    ) -> tuple[type["ProviderError"], tuple[ErrorCode, str, str | None]]:
        return (type(self), (self.code, self.log_message, self.provider_message))


class ExchangeRefused(Exception):
    """The adapter refused an exchange before connecting: a second one in a call, or one outside
    any call. It isn't a `requests.ConnectionError`, so the wrapper doesn't catch it, and it ends
    the call. A refused exchange sent nothing, so it isn't recorded.
    """


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
    """Executes the one supported screen-backtest request, and returns the captured provider
    evidence (docs/contracts.md, protocols).

    The caller authenticates with `authenticate`, writes the start record, and only then calls
    `screen_backtest`, at most once for each approved send. `exchanges` gives every exchange so
    far, in order, at any time, including after an interrupt. Neither call retries anything.
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

    def close(self) -> None:
        """Closes the client's connections."""
        ...


class _Recorded:
    """One exchange, recorded before it's sent. Its ending is set in one assignment, so an
    interrupt never leaves a result without its status."""

    __slots__ = ("ended", "request")

    def __init__(self, request: str) -> None:
        self.request = request
        self.ended: Exchange | None = None

    def end(self, result: Literal["not_connected", "interrupted"]) -> None:
        self.ended = Exchange(request=self.request, result=result, status=None, note=None)

    def exchange(self) -> Exchange:
        if self.ended is not None:
            return self.ended
        return Exchange(request=self.request, result="interrupted", status=None, note=None)


@dataclass
class _Call:
    """One call to the wrapper, during which the adapter allows one exchange."""

    kind: CallKind
    recorded: _Recorded | None = None
    refused: bool = False
    body: bytes | None = field(default=None, repr=False)
    """The body of a 200 on the request's exchange, held in case the wrapper can't decode it."""


def _not_connected(error: Exception) -> bool:
    """Whether `error` proves the request was never sent: the `requests` error wraps a `urllib3`
    `MaxRetryError` whose reason, after unwrapping a `ProxyError`, is a `ConnectTimeoutError`.
    That's the test `urllib3`'s `Retry._is_connection_error` applies, and it covers a failed name
    lookup, a refused or unreachable connection, and a connect timeout."""
    if not isinstance(error, requests.RequestException) or not error.args:
        return False
    wrapped = cast(object, error.args[0])
    if not isinstance(wrapped, MaxRetryError):
        return False
    reason: object = wrapped.reason
    if isinstance(reason, ProxyError):
        reason = reason.original_error
    return isinstance(reason, ConnectTimeoutError)


def _path(url: str | None) -> str:
    """The path of a request's URL, without its query, which could carry data."""
    return urlsplit(url or "").path or "/"


class ExchangeRecordingAdapter(HTTPAdapter):
    """Records each exchange the wrapper makes, and allows one exchange in each call (ADR 0006).

    It records the method and path, then the result: `response` with the HTTP status,
    `not_connected`, or `interrupted`. It keeps no headers, tokens, or exception objects, and no
    body except a 200's on the request's exchange. It changes no request or response, and passes
    every error on unchanged. `urllib3` retries stay at `requests`' default, `Retry(0, read=False)`.
    """

    def __init__(self) -> None:
        super().__init__()
        self._recorded: list[_Recorded] = []
        self._call: _Call | None = None

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        """Every exchange so far, in order. One still without a result reads as `interrupted`."""
        return tuple(recorded.exchange() for recorded in self._recorded)

    @contextmanager
    def call(self, kind: CallKind) -> Generator[_Call]:
        """Opens one call to the wrapper. Exchanges are refused outside a call."""
        if self._call is not None:
            raise RuntimeError("calls to the wrapper don't nest")
        self._call = _Call(kind)
        try:
            yield self._call
        finally:
            self._call = None

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float | None, float | None] | None = None,
        verify: bool | str = True,
        cert: str | tuple[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> requests.Response:
        call = self._call
        if call is None or call.recorded is not None:
            if call is not None:
                call.refused = True
            _logger.warning(
                "Refused an exchange before connecting: each call to the wrapper gets one.",
                extra={"event": "provider.request.refused"},
            )
            raise ExchangeRefused("Trial Folio allows one exchange in each call to the wrapper")
        recorded = _Recorded(f"{request.method} {_path(request.url)}")
        self._recorded.append(recorded)
        call.recorded = recorded
        _logger.info("Sending %s.", recorded.request, extra={"event": "provider.request.started"})
        started = time.monotonic()
        try:
            response = super().send(
                request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies
            )
            # Read here, so a body that breaks off, or times out, is this exchange's ending.
            body = response.content
        except Exception as error:
            recorded.end("not_connected" if _not_connected(error) else "interrupted")
            _logger.info(
                "%s ended %s after %.3f s.",
                recorded.request,
                recorded.exchange().result,
                time.monotonic() - started,
                extra={"event": "provider.request.failed"},
            )
            raise
        status = response.status_code
        if 100 <= status <= 599:
            recorded.ended = Exchange(
                request=recorded.request, result="response", status=status, note=None
            )
        else:
            # Not an HTTP status (RFC 9110, section 15), so no complete response arrived.
            recorded.end("interrupted")
        if call.kind == "request" and status == 200:
            call.body = body
        _logger.info(
            "%s got HTTP %d after %.3f s.",
            recorded.request,
            status,
            time.monotonic() - started,
            extra={"event": "provider.request.completed"},
        )
        return response


class _Wrapper(Protocol):
    """The part of `p123api.Client` 3.1.0 Trial Folio uses, typed: the package ships no types."""

    _session: requests.Session

    def set_max_request_retries(self, retries: int) -> None: ...
    def set_timeout(self, timeout: int) -> None: ...
    def get_token(self) -> str | None: ...
    def auth(self) -> None: ...
    def screen_backtest(self, params: dict[str, object], to_pandas: bool = False) -> object: ...
    def close(self) -> None: ...


class P123ScreenBacktestClient:
    """`ScreenBacktestClient` over `p123api`'s `Client`, configured as the module says."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        endpoint: str | None = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """`endpoint` and `timeout` are for tests only (docs/contracts.md, credentials): without
        `endpoint`, the wrapper's default, Portfolio123's API, applies."""
        if endpoint is None:
            client = p123api.Client(api_id=credentials.api_id, api_key=credentials.api_key)
        else:
            client = p123api.Client(
                api_id=credentials.api_id, api_key=credentials.api_key, endpoint=endpoint
            )
        self._wrapper = cast(_Wrapper, client)
        self._secrets = (credentials.api_id, credentials.api_key)
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
                failure = _authentication_failure(
                    call, self._provider_message(error, "API authentication failed: "), error
                )
            else:
                return
        raise failure

    def screen_backtest(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        if not self.authenticated:
            # Otherwise the wrapper would authenticate inside the request's call, and the adapter
            # would refuse the request as its second exchange.
            raise RuntimeError("Trial Folio authenticates with its own call before a request")
        with self._adapter.call("request") as call:
            try:
                payload = self._wrapper.screen_backtest(dict(params), to_pandas=False)
            except Exception as error:  # noqa: BLE001 (classified, as above)
                body = call.body
                if body is not None:
                    # Whatever the wrapper raised after the 200, it didn't return a decoded
                    # response, so the body is kept undecoded (HTTP exchanges).
                    return UndecodedResponse(body)
                failure = _request_failure(
                    call, self._provider_message(error, "API request failed: "), error
                )
            else:
                return DecodedResponse(payload)
        raise failure

    def close(self) -> None:
        self._wrapper.close()

    def _provider_message(self, error: Exception, prefix: str) -> str | None:
        """Portfolio123's own text in the wrapper's message, sanitized, if it carries any.

        Only a plain `ClientException` carries it, after `prefix`; `ClientItemNotFoundException`
        carries the wrapper's own text. Sanitizing redacts the credentials and the token, makes
        control characters spaces, collapses whitespace, and keeps at most 300 characters.
        """
        if type(error) is not p123api.ClientException:
            return None
        text = str(error)
        if not text.startswith(prefix):
            return None
        text = text.removeprefix(prefix)
        secrets = sorted(
            (secret for secret in (*self._secrets, self._wrapper.get_token()) if secret),
            key=len,
            reverse=True,
        )
        # Match once, so replacing an ID can't expose the rest of a key or token.
        text = re.sub("|".join(re.escape(secret) for secret in secrets), "[redacted]", text)
        text = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in text)
        text = " ".join(text.split())
        if len(text) > _MAX_PROVIDER_MESSAGE:
            text = text[: _MAX_PROVIDER_MESSAGE - 1].rstrip() + "…"
        return text or None


_CREDENTIALS_HINT: Final = (
    "Check the API ID and key, which Portfolio123's website lists under DataMiner & API."
)
_NOT_SENT: Final = "The backtest request wasn't sent."
_MAY_BE_CHARGED: Final = "The request may have been charged."


def _authentication_failure(
    call: _Call, provider_message: str | None, error: Exception
) -> ProviderError:
    """The failure of Trial Folio's authentication call, from 0.1.0's failure table."""
    exchange = call.recorded.exchange() if call.recorded is not None else None
    status = exchange.status if exchange is not None else None
    if exchange is None or status == 200:
        return ProviderError(
            "internal.unexpected",
            f"Trial Folio's authentication call failed unexpectedly ({type(error).__name__})."
            f" {_NOT_SENT} This is a defect in Trial Folio; please report it.",
        )
    if exchange.result == "not_connected":
        return ProviderError(
            "provider.unavailable",
            "Couldn't connect to Portfolio123 to authenticate: the connection was never"
            f" established. {_NOT_SENT} Check the network connection, and try again.",
        )
    if status is None:
        return ProviderError(
            "provider.unavailable",
            "The connection to Portfolio123 broke before Trial Folio's authentication call got a"
            f" complete response. {_NOT_SENT} Try again.",
        )
    if status >= 500:
        return ProviderError(
            "provider.unavailable",
            f"Portfolio123 answered Trial Folio's authentication call with HTTP {status}, a"
            f" server error. {_NOT_SENT} Try again later.",
        )
    match status:
        case 400:
            return ProviderError(
                "provider.auth_failed",
                f"Portfolio123 rejected the API key as invalid (HTTP 400). {_CREDENTIALS_HINT}"
                f" {_NOT_SENT}",
            )
        case 401:
            return ProviderError(
                "provider.auth_failed",
                "Portfolio123 rejected the API ID and key (HTTP 401): the combination is invalid,"
                f" or the key is inactive. {_CREDENTIALS_HINT} {_NOT_SENT}",
            )
        case 402:
            return ProviderError(
                "provider.auth_failed",
                "Portfolio123 requires a paying subscription for API access (HTTP 402)."
                f" {_NOT_SENT}",
            )
        case 403:
            return ProviderError(
                "provider.auth_failed",
                f"Portfolio123 refused authentication (HTTP 403). {_CREDENTIALS_HINT} Also check"
                f" that the account has API access. {_NOT_SENT}",
                provider_message,
            )
        case 406:
            return ProviderError(
                "provider.auth_failed",
                f"Portfolio123 reports the account as inactive (HTTP 406). {_NOT_SENT}",
            )
        case _:
            refusal = (
                " Trial Folio doesn't follow redirects, so it refused the next exchange."
                if call.refused
                else ""
            )
            return ProviderError(
                "provider.request_rejected",
                f"Portfolio123 answered Trial Folio's authentication call with HTTP {status}."
                f" That isn't a problem with the API ID or key.{refusal} {_NOT_SENT} Try again"
                " later, and report it if it persists.",
                provider_message,
            )


def _request_failure(call: _Call, provider_message: str | None, error: Exception) -> ProviderError:
    """The failure of the request's call, from 0.1.0's failure table."""
    exchange = call.recorded.exchange() if call.recorded is not None else None
    if exchange is None:
        return ProviderError(
            "internal.unexpected",
            f"The screen backtest call failed unexpectedly ({type(error).__name__}) before"
            " sending anything, so the request wasn't sent. This is a defect in Trial Folio;"
            " please report it.",
        )
    if exchange.result == "not_connected":
        return ProviderError(
            "provider.unavailable",
            "Couldn't connect to Portfolio123: the connection was never established, so the"
            " screen backtest request wasn't sent, and wasn't charged. Check the network"
            " connection, and run the command again.",
        )
    unknown = (
        "Its outcome is unknown, and Trial Folio never retries it automatically: check the"
        " account's API credits on Portfolio123's website before running the command again."
    )
    status = exchange.status
    if status is None:
        return ProviderError(
            "provider.outcome_unknown",
            "The connection to Portfolio123 broke before the screen backtest request got a"
            f" complete response, for example after a timeout or a reset. {_MAY_BE_CHARGED}"
            f" {unknown}",
        )
    if status >= 500:
        return ProviderError(
            "provider.outcome_unknown",
            f"Portfolio123 answered the screen backtest request with HTTP {status}, a server"
            f" error. {_MAY_BE_CHARGED} {unknown}",
        )
    again = "Running the command again is a new attempt."
    if status == 400:
        return ProviderError(
            "provider.unsupported_capability",
            "Portfolio123 rejected the screen backtest request (HTTP 400): it doesn't support a"
            f" setting or value in it. {_MAY_BE_CHARGED} Check the configuration before running"
            f" the command again, which is a new attempt.",
            provider_message,
        )
    if status == 402:
        return ProviderError(
            "provider.quota_exceeded",
            "Portfolio123 refused the screen backtest request because the account's API quota or"
            f" credits are exhausted (HTTP 402). {_MAY_BE_CHARGED} Check the account's API"
            " credits on Portfolio123's website before running the command again.",
        )
    if status in _REAUTHENTICATES:
        refusal = (
            " Trial Folio refused the wrapper's re-authentication, a second exchange in one"
            " call, so the request wasn't sent again."
            if call.refused
            else ""
        )
        return ProviderError(
            "provider.auth_failed",
            f"Portfolio123 refused the screen backtest request's authorization (HTTP {status}),"
            f" right after Trial Folio authenticated.{refusal} {_MAY_BE_CHARGED} Check the API"
            f" key's status on Portfolio123's website. {again}",
        )
    if call.refused and status in _REDIRECTS:
        return ProviderError(
            "provider.request_rejected",
            "Portfolio123 answered the screen backtest request with a redirect (HTTP"
            f" {status}). Trial Folio doesn't follow redirects, so it refused the next exchange,"
            f" and the request wasn't sent again. {_MAY_BE_CHARGED} {again}",
        )
    return ProviderError(
        "provider.request_rejected",
        f"Portfolio123 rejected the screen backtest request with HTTP {status}."
        f" {_MAY_BE_CHARGED} Wait before running the command again, which is a new attempt.",
        provider_message,
    )
