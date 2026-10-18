"""`trialfolio demo`'s packaged synthetic configuration and response, and the client that serves
the response without any network access (release 0.1.0, included scope).

The demo writes a run as `trialfolio run` writes one, through the same steps and records, so it
shows every file of a run, in every 1.0.0 schema, and `trialfolio report` reads it like any run.
Its manifest labels it synthetic, with the approval `not_required`, and its report says that every
value is invented and nothing was sent.

`SyntheticScreenBacktestClient` records the exchanges a successful call records, `POST /auth` and
then `POST /screen/backtest`, each a 200, because the 1.0.0 attempt record holds an attempt that
succeeded only with them. So the demo's records read as a real run's do: `possibly_charged` and
one provider request. They're invented, like its values: no socket is opened, and the packaged
response carries no `cost`, so the run reports none.

From 0.4.0, it also answers a `rank_update`, with an empty object, and records its `POST /rank`
exchange, a 200, so the core can execute, with it, a screen run or an experiment whose ranking is
a definition, which no 0.4.0 command does: `trialfolio demo` still runs its packaged
configuration. Such an execution takes the ranking lock all the same (docs/contracts.md, CLI
behavior).

It also answers a `rank_get` with an invented system, the response its caller gives, in the layout
of `p123api-rank-get` version 1, and records its `GET /rank` exchange, a 200, so the core can take,
with it, a ranking snapshot, which no 0.4.0 command does either. Such a snapshot is synthetic, and
takes no lock, as no snapshot does.
"""

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Final

from trialfolio.contracts.attempt import Exchange
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    RANK_GET_REQUEST,
    RANK_UPDATE_REQUEST,
    SCREEN_BACKTEST_REQUEST,
)
from trialfolio.provider import DecodedResponse, ScreenBacktestResponse

CONFIGURATION_NAME: Final = "demo screen configuration"
"""How messages name the packaged configuration."""


def configuration_bytes() -> bytes:
    """The packaged synthetic screen configuration."""
    return files("trialfolio").joinpath("demo_data", "screen.yaml").read_bytes()


def response_bytes() -> bytes:
    """The packaged synthetic response, in the layout of `p123api-screen-backtest` version 1."""
    return files("trialfolio").joinpath("demo_data", "response.json").read_bytes()


class SyntheticScreenBacktestClient:
    """A `ScreenBacktestClient` that sends nothing: it answers the backtest with a synthetic
    response, a `rank_update` with an empty object, and a `rank_get` with an invented system, and
    records the exchanges a successful call would."""

    def __init__(self, response: bytes, *, system: bytes | None = None) -> None:
        """`response` is the synthetic response's JSON, and `system` the invented system's, a
        `rank_get` response, for a client that answers one. Raises `ValueError` if either isn't
        JSON."""
        self._payload: object = json.loads(response)
        self._system: object = None if system is None else json.loads(system)
        self._exchanges: list[Exchange] = []

    @property
    def authenticated(self) -> bool:
        return any(exchange.request == AUTHENTICATION_REQUEST for exchange in self._exchanges)

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        return tuple(self._exchanges)

    def authenticate(self) -> None:
        self._exchanges.append(_answered(AUTHENTICATION_REQUEST))

    def screen_backtest(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        if not self.authenticated:
            raise RuntimeError("Trial Folio authenticates with its own call before a request")
        self._exchanges.append(_answered(SCREEN_BACKTEST_REQUEST))
        return DecodedResponse(self._payload)

    def rank_update(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        """Answers with an empty object, and writes no ranking system: nothing is sent."""
        if not self.authenticated:
            raise RuntimeError("Trial Folio authenticates with its own call before a request")
        self._exchanges.append(_answered(RANK_UPDATE_REQUEST))
        return DecodedResponse({})

    def rank_get(self, name: str) -> ScreenBacktestResponse:
        """Answers with the invented system its caller gave, whatever `name` is: nothing is
        sent, and nothing is read from an account."""
        if not self.authenticated:
            raise RuntimeError("Trial Folio authenticates with its own call before a request")
        if self._system is None:
            raise RuntimeError("the demo's client answers a rank_get with the system it's given")
        self._exchanges.append(_answered(RANK_GET_REQUEST))
        return DecodedResponse(self._system)

    def close(self) -> None:
        """Nothing to close: no connection was opened."""


def _answered(request: str) -> Exchange:
    return Exchange(request=request, result="response", status=200, note=None)
