"""The transport adapter that records each HTTP exchange the wrapper makes, and allows one exchange
in each call to the wrapper (docs/contracts.md, HTTP exchanges; ADR 0006).

Its events, `provider.request.started`, `completed`, `failed`, and `refused`, log as
`trialfolio.provider`, the name they had before the provider was a package (docs/refactoring.md,
decision 11).
"""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal, cast
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, ProxyError

from trialfolio.contracts.attempt import Exchange

_logger = logging.getLogger("trialfolio.provider")

type CallKind = Literal["authentication", "request"]


class ExchangeRefused(Exception):
    """The adapter refused an exchange before connecting: a second one in a call, or one outside
    any call. It isn't a `requests.ConnectionError`, so the wrapper doesn't catch it, and it ends
    the call. A refused exchange sent nothing, so it isn't recorded.
    """


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

    @property
    def exchange(self) -> Exchange | None:
        """The call's exchange, or None when it made none."""
        return self.recorded.exchange() if self.recorded is not None else None


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
        call = self._admitted()
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

    def _admitted(self) -> _Call:
        """The call an exchange is made in, unless it's refused before connecting: a second
        exchange in the call, or one outside any call."""
        call = self._call
        if call is not None and call.recorded is None:
            return call
        if call is not None:
            call.refused = True
        _logger.warning(
            "Refused an exchange before connecting: each call to the wrapper gets one.",
            extra={"event": "provider.request.refused"},
        )
        raise ExchangeRefused("Trial Folio allows one exchange in each call to the wrapper")
