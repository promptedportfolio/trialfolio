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
"""

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Final

from trialfolio.contracts.attempt import Exchange
from trialfolio.contracts.common import AUTHENTICATION_REQUEST, SCREEN_BACKTEST_REQUEST
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
    """A `ScreenBacktestClient` that sends nothing: it answers the request with a synthetic
    response, and records the exchanges a successful call would."""

    def __init__(self, response: bytes) -> None:
        """`response` is the synthetic response's JSON. Raises `ValueError` if it isn't JSON."""
        self._payload: object = json.loads(response)
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

    def close(self) -> None:
        """Nothing to close: no connection was opened."""


def _answered(request: str) -> Exchange:
    return Exchange(request=request, result="response", status=200, note=None)
