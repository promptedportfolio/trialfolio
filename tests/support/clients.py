"""Clients of the fake Portfolio123 server, for the provider's tests: a request body whose contents
don't matter to the transport, the type of the provider conftest's `make_client`, and the
authentication of a client against the server.

TS-T04 moved them here from the provider's conftest, which keeps its fixtures.
"""

from collections.abc import Callable
from typing import Final

from tests.support.fake_portfolio123 import AUTHENTICATED, FakePortfolio123
from trialfolio.provider import P123ScreenBacktestClient

PARAMS: Final = {"screen": {"universe": "SP500"}, "startDt": "2016-01-01", "slippage": 0.25}
"""A request body. Its contents don't matter to the transport."""

type ClientFactory = Callable[..., P123ScreenBacktestClient]
"""Makes a client for the fake server, with the canary credentials, which the fixture closes."""


def authenticate(server: FakePortfolio123, client: P123ScreenBacktestClient) -> None:
    """Authenticates `client` against the fake server, which issues the canary token."""
    server.reply("/auth", AUTHENTICATED)
    client.authenticate()
