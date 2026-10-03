"""The provider tests' boundaries: the fake Portfolio123 server and socket faults below `urllib3`,
with the real `p123api`, `requests`, and `urllib3` above them (AGENTS.md, verification
expectations)."""

from collections.abc import Callable, Iterator

import pytest

from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.socket_faults import SocketFaults
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS, Credentials, P123ScreenBacktestClient

PARAMS = {"screen": {"universe": "SP500"}, "startDt": "2016-01-01", "slippage": 0.25}
"""A request body. Its contents don't matter to the transport."""

type ClientFactory = Callable[..., P123ScreenBacktestClient]


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    fake = FakePortfolio123()
    yield fake
    fake.close()


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> SocketFaults:
    return SocketFaults(monkeypatch)


@pytest.fixture
def make_client(server: FakePortfolio123) -> Iterator[ClientFactory]:
    """Makes clients for the fake server, with the canary credentials, and closes them after."""
    made: list[P123ScreenBacktestClient] = []

    def make(
        *, endpoint: str | None = None, timeout: int = REQUEST_TIMEOUT_SECONDS
    ) -> P123ScreenBacktestClient:
        client = P123ScreenBacktestClient(
            Credentials(canaries.API_ID, canaries.API_KEY),
            endpoint=endpoint or server.endpoint,
            timeout=timeout,
        )
        made.append(client)
        return client

    yield make
    for client in made:
        client.close()


@pytest.fixture
def client(make_client: ClientFactory) -> P123ScreenBacktestClient:
    return make_client()


def authenticate(server: FakePortfolio123, client: P123ScreenBacktestClient) -> None:
    """Authenticates `client` against the fake server, which issues the canary token."""
    server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
    client.authenticate()
