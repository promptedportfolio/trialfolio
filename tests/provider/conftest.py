"""The provider tests' boundaries: the fake Portfolio123 server, `tests/conftest.py`'s, and socket
faults below `urllib3`, with the real `p123api`, `requests`, and `urllib3` above them (AGENTS.md,
verification expectations).

TS-T04 moved the helpers its tests import, `PARAMS`, `ClientFactory`, and `authenticate`, to
`tests/support/clients.py`, so this file keeps only the fixtures.
"""

from collections.abc import Iterator

import pytest

from tests.support.clients import ClientFactory
from tests.support.fake_portfolio123 import CREDENTIALS, FakePortfolio123
from tests.support.socket_faults import SocketFaults
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS, P123ScreenBacktestClient


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> SocketFaults:
    return SocketFaults(monkeypatch)


@pytest.fixture
def make_client(server: FakePortfolio123) -> Iterator[ClientFactory]:
    """Makes clients for the fake server, with the canary credentials, and closes them after."""
    made: list[P123ScreenBacktestClient] = []

    def make(
        *,
        endpoint: str | None = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        snapshot: bool = False,
    ) -> P123ScreenBacktestClient:
        client = P123ScreenBacktestClient(
            CREDENTIALS,
            endpoint=endpoint or server.endpoint,
            timeout=timeout,
            snapshot=snapshot,
        )
        made.append(client)
        return client

    yield make
    for client in made:
        client.close()


@pytest.fixture
def client(make_client: ClientFactory) -> P123ScreenBacktestClient:
    return make_client()
