"""A failed call's error: `ProviderError`, with the code and message 0.1.0's failure table gives
the call's ending (docs/releases/0.1.0-api-execution.md, failure behavior; docs/contracts.md,
HTTP exchanges, credentials, and errors).

Each call has a table of messages: `_AUTHENTICATION`, Trial Folio's own authentication call's, and
`_REQUEST`, a request's, which a `rank_update`'s follows too (sending a definition). A table's
`message` classifies what the call's exchange shows: no exchange, not connected, no complete
response, a 5xx, or a status, with a message of its own or the table's other. Where the adapter
refused the call's next exchange, a message can say so. `AUTHENTICATION`, `BACKTEST`, and
`RANK_UPDATE` fill a table's messages for their call, and `CallMessages.failure` builds the error.

A message that calls for it ends with Portfolio123's own text, from the wrapper's message,
sanitized: `_provider_message` reads only the exception's type and message, never anything else
on it.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Final

import p123api  # pyright: ignore[reportMissingTypeStubs]: the package ships no types

from trialfolio.contracts.attempt import Exchange
from trialfolio.errors import ErrorCode, TrialFolioError

_MAX_PROVIDER_MESSAGE: Final = 300
"""The most characters of Portfolio123's own message an error keeps."""


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
            full = f'{message}{_PROVIDER_MESSAGE}"{provider_message}"'
        super().__init__(code, full, message)
        self.provider_message = provider_message

    def __reduce__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
    ) -> tuple[type["ProviderError"], tuple[ErrorCode, str, str | None]]:
        return (type(self), (self.code, self.log_message, self.provider_message))


_PROVIDER_MESSAGE: Final = " Portfolio123's message: "


def provider_message_of(message: str) -> str | None:
    """Portfolio123's own text in a `ProviderError`'s full message, as an attempt record keeps
    it, or None when it carries none. Trial Folio's own text before it never holds the marker."""
    _, marker, quoted = message.partition(_PROVIDER_MESSAGE)
    if not marker or not quoted.startswith('"') or not quoted.endswith('"'):
        return None
    return quoted[1:-1]


def _provider_message(error: Exception, prefix: str, secrets: Iterable[str | None]) -> str | None:
    """Portfolio123's own text in the wrapper's message, sanitized, if it carries any.

    Only a plain `ClientException` carries it, after `prefix`; `ClientItemNotFoundException`
    carries the wrapper's own text. Sanitizing redacts `secrets`, the credentials and the token,
    makes control characters spaces, collapses whitespace, and keeps at most 300 characters.
    """
    if type(error) is not p123api.ClientException:
        return None
    text = str(error)
    if not text.startswith(prefix):
        return None
    text = text.removeprefix(prefix)
    longest_first = sorted((secret for secret in secrets if secret), key=len, reverse=True)
    # Match once, so replacing an ID can't expose the rest of a key or token.
    text = re.sub("|".join(re.escape(secret) for secret in longest_first), "[redacted]", text)
    text = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in text)
    text = " ".join(text.split())
    if len(text) > _MAX_PROVIDER_MESSAGE:
        text = text[: _MAX_PROVIDER_MESSAGE - 1].rstrip() + "…"
    return text or None


@dataclass(frozen=True)
class _Message:
    """One failure's error: its code, and its text, whose fields are filled with the exchange's
    status, `{status}`, the type of the wrapper's exception, `{error}`, and its call's fields."""

    code: ErrorCode
    text: str
    quoted: bool = False
    """Whether the message ends with Portfolio123's own text, when the wrapper's carries some."""
    refused: "_Message | None" = None
    """The message instead when the adapter refused the call's next exchange: the wrapper's
    re-authentication after a 401 or 403, or a redirect `requests` would follow."""


@dataclass(frozen=True)
class _Table:
    """A call's table of messages, by what its exchange shows."""

    no_exchange: _Message
    """The call failed before its exchange was recorded, so nothing was sent."""
    not_connected: _Message
    """The connection was provably never established, so nothing was sent."""
    broken_off: _Message
    """No complete response arrived: the exchange is `interrupted`."""
    server_error: _Message
    """A 5xx."""
    statuses: Mapping[int, _Message]
    """Each other status that has a message of its own."""
    other: _Message
    """Every other status."""

    def message(self, exchange: Exchange | None) -> _Message:
        """The classifier: the message for what a failed call's exchange shows."""
        if exchange is None:
            return self.no_exchange
        if exchange.result == "not_connected":
            return self.not_connected
        if exchange.status is None:
            return self.broken_off
        if exchange.status >= 500:
            return self.server_error
        return self.statuses.get(exchange.status, self.other)

    def messages(self) -> Iterator[_Message]:
        """Every message in the table, each one's refused message after it."""
        endings = (self.no_exchange, self.not_connected, self.broken_off, self.server_error)
        for message in (*endings, *self.statuses.values(), self.other):
            yield message
            if message.refused is not None:
                yield message.refused


@dataclass(frozen=True)
class CallMessages:
    """What a call's failures say: its table of messages, what fills their fields, and the
    wrapper's prefix to Portfolio123's own text in its exception's message."""

    prefix: str
    table: _Table
    fields: Mapping[str, str]

    def __post_init__(self) -> None:
        # Each message is filled once here, so a field it misspells fails on import, as a name
        # an f-string misspells fails the type check, not only when that failure happens.
        for message in self.table.messages():
            message.text.format(status=0, error="", **self.fields)

    def failure(
        self,
        exchange: Exchange | None,
        refused: bool,
        error: Exception,
        secrets: Iterable[str | None],
    ) -> ProviderError:
        """The error of a failed call: the message for its `exchange`, or the message for its
        refused next exchange when the adapter `refused` one, naming the type of the wrapper's
        exception, `error`, and ending with Portfolio123's own text, sanitized of `secrets`, when
        the message calls for it."""
        message = self.table.message(exchange)
        if refused and message.refused is not None:
            message = message.refused
        status = exchange.status if exchange is not None else None
        text = message.text.format(status=status, error=type(error).__name__, **self.fields)
        provider_message = (
            _provider_message(error, self.prefix, secrets) if message.quoted else None
        )
        return ProviderError(message.code, text, provider_message)


_AUTHENTICATION_UNEXPECTED: Final = _Message(
    "internal.unexpected",
    "Trial Folio's authentication call failed unexpectedly ({error}). {not_sent} This is a defect"
    " in Trial Folio; please report it.",
)

_AUTHENTICATION: Final = _Table(
    no_exchange=_AUTHENTICATION_UNEXPECTED,
    not_connected=_Message(
        "provider.unavailable",
        "Couldn't connect to Portfolio123 to authenticate: the connection was never established."
        " {not_sent} Check the network connection, and try again.",
    ),
    broken_off=_Message(
        "provider.unavailable",
        "The connection to Portfolio123 broke before Trial Folio's authentication call got a"
        " complete response. {not_sent} Try again.",
    ),
    server_error=_Message(
        "provider.unavailable",
        "Portfolio123 answered Trial Folio's authentication call with HTTP {status}, a server"
        " error. {not_sent} Try again later.",
    ),
    statuses={
        # The token arrived, and the call failed anyway.
        200: _AUTHENTICATION_UNEXPECTED,
        400: _Message(
            "provider.auth_failed",
            "Portfolio123 rejected the API key as invalid (HTTP 400). {credentials} {not_sent}",
        ),
        401: _Message(
            "provider.auth_failed",
            "Portfolio123 rejected the API ID and key (HTTP 401): the combination is invalid, or"
            " the key is inactive. {credentials} {not_sent}",
        ),
        402: _Message(
            "provider.auth_failed",
            "Portfolio123 requires a paying subscription for API access (HTTP 402). {not_sent}",
        ),
        403: _Message(
            "provider.auth_failed",
            "Portfolio123 refused authentication (HTTP 403). {credentials} Also check that the"
            " account has API access. {not_sent}",
            quoted=True,
        ),
        406: _Message(
            "provider.auth_failed",
            "Portfolio123 reports the account as inactive (HTTP 406). {not_sent}",
        ),
    },
    other=_Message(
        "provider.request_rejected",
        "Portfolio123 answered Trial Folio's authentication call with HTTP {status}. That isn't a"
        " problem with the API ID or key. {not_sent} Try again later, and report it if it"
        " persists.",
        quoted=True,
        refused=_Message(
            "provider.request_rejected",
            "Portfolio123 answered Trial Folio's authentication call with HTTP {status}. That isn't"
            " a problem with the API ID or key. Trial Folio doesn't follow redirects, so it refused"
            " the next exchange. {not_sent} Try again later, and report it if it persists.",
            quoted=True,
        ),
    ),
)

AUTHENTICATION: Final = CallMessages(
    "API authentication failed: ",
    _AUTHENTICATION,
    {
        "not_sent": "The backtest request wasn't sent.",
        "credentials": (
            "Check the API ID and key, which Portfolio123's website lists under DataMiner & API."
        ),
    },
)
"""The messages of Trial Folio's own authentication call."""

_REJECTED: Final = _Message(
    "provider.request_rejected",
    "Portfolio123 rejected the {name} with HTTP {status}. {may_be_charged}{after} Wait before"
    " running the command again, which is a new attempt.",
    quoted=True,
)

_REQUEST: Final = _Table(
    no_exchange=_Message(
        "internal.unexpected",
        "The {call} call failed unexpectedly ({error}) before sending anything, so the request"
        " wasn't sent.{after} This is a defect in Trial Folio; please report it.",
    ),
    not_connected=_Message(
        "provider.unavailable",
        "Couldn't connect to Portfolio123: the connection was never established, so the {name}"
        " wasn't sent, and wasn't charged.{after} Check the network connection, and run the"
        " command again.",
    ),
    broken_off=_Message(
        "provider.outcome_unknown",
        "The connection to Portfolio123 broke before the {name} got a complete response, for"
        " example after a timeout or a reset. {may_be_charged}{after} {unknown}",
    ),
    server_error=_Message(
        "provider.outcome_unknown",
        "Portfolio123 answered the {name} with HTTP {status}, a server error."
        " {may_be_charged}{after} {unknown}",
    ),
    statuses={
        # Portfolio123 rejected a setting or value in the request. It answered a rule that names
        # no factor with a 409 (D-38).
        **dict.fromkeys(
            (400, 409),
            _Message(
                "provider.unsupported_capability",
                "Portfolio123 rejected the {name} (HTTP {status}): {rejected}."
                " {may_be_charged}{after} Check {check} before running the command again, which is"
                " a new attempt.",
                quoted=True,
            ),
        ),
        402: _Message(
            "provider.quota_exceeded",
            "Portfolio123 refused the {name} because the account's API quota or credits are"
            " exhausted (HTTP 402). {may_be_charged}{after} Check the account's API credits on"
            " Portfolio123's website before running the command again.",
        ),
        # After a 401 or 403, the wrapper drops its token, re-authenticates, and resends.
        **dict.fromkeys(
            (401, 403),
            _Message(
                "provider.auth_failed",
                "Portfolio123 refused the {name}'s authorization (HTTP {status}), right after"
                " Trial Folio authenticated. {may_be_charged}{after} Check the API key's status on"
                " Portfolio123's website. {again}",
                refused=_Message(
                    "provider.auth_failed",
                    "Portfolio123 refused the {name}'s authorization (HTTP {status}), right after"
                    " Trial Folio authenticated. Trial Folio refused the wrapper's"
                    " re-authentication, a second exchange in one call, so the request wasn't sent"
                    " again. {may_be_charged}{after} Check the API key's status on Portfolio123's"
                    " website. {again}",
                ),
            ),
        ),
        # `requests` follows these statuses when the response has a `Location` header.
        **dict.fromkeys(
            (301, 302, 303, 307, 308),
            replace(
                _REJECTED,
                refused=_Message(
                    "provider.request_rejected",
                    "Portfolio123 answered the {name} with a redirect (HTTP {status}). Trial Folio"
                    " doesn't follow redirects, so it refused the next exchange, and the request"
                    " wasn't sent again. {may_be_charged}{after} {again}",
                ),
            ),
        ),
    },
    other=_REJECTED,
)


def _request(name: str, *, rejected: str, check: str, after: str = "") -> CallMessages:
    """The messages of a request's call: `name` is the request, as in "the screen backtest
    request"; `rejected` what a 400 or a 409 says Portfolio123 doesn't accept in it; `check` what
    to check before running the command again after one; and `after` what follows the request's
    own ending: for a `rank_update`, that its backtest wasn't sent."""
    return CallMessages(
        "API request failed: ",
        _REQUEST,
        {
            "name": name,
            "call": name.removesuffix(" request"),
            "rejected": rejected,
            "check": check,
            "after": after,
            "may_be_charged": "The request may have been charged.",
            "unknown": (
                "Its outcome is unknown, and Trial Folio never retries it automatically: check"
                " the account's API credits on Portfolio123's website before running the command"
                " again."
            ),
            "again": "Running the command again is a new attempt.",
        },
    )


BACKTEST: Final = _request(
    "screen backtest request",
    rejected="it doesn't support a setting or value in it",
    check="the configuration",
)
"""The messages of the screen backtest request's call."""

RANK_UPDATE: Final = _request(
    "rank_update request",
    rejected="it doesn't accept the ranking definition, or a value sent with it",
    check="the configuration's ranking definition",
    after=(
        " That request writes the case's ranking definition into ApiRankingSystem, so the"
        " case's screen backtest wasn't sent."
    ),
)
"""The messages of the `rank_update` request's call, which follow a request's (sending a
definition)."""
