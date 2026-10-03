"""The environment can't redirect or expose the credentials: the client turns off `requests`'
environment settings on the wrapper's session.

Traces to R01-AC32 and docs/contracts.md, credentials. `SSLKEYLOGFILE` is the CLI's, and its test
is in tests/interface/test_run_capture.py.
"""

import json
import socket
from pathlib import Path

import pytest

from tests.provider.conftest import PARAMS, authenticate
from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.provider import P123ScreenBacktestClient


@pytest.fixture
def closed_port() -> int:
    """A localhost port nothing listens on."""
    with socket.create_server(("127.0.0.1", 0)) as listener:
        return listener.getsockname()[1]


def test_proxies_certificate_bundles_and_netrc_in_the_environment_are_ignored(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    closed_port: int,
) -> None:
    proxy = f"http://127.0.0.1:{closed_port}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, proxy)
    # The suite sets these to *, which would bypass the proxies anyway.
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    missing = str(tmp_path / "missing-bundle.pem")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", missing)
    monkeypatch.setenv("CURL_CA_BUNDLE", missing)
    netrc = tmp_path / "netrc"
    netrc.write_text("default login netrc-login password netrc-password\n")
    netrc.chmod(0o600)
    monkeypatch.setenv("NETRC", str(netrc))
    server.reply("/screen/backtest", Reply(200, b"{}"))

    authenticate(server, client)
    client.screen_backtest(PARAMS)

    # Both went straight to the endpoint, not to the proxy, which would have refused them.
    assert server.requests() == ["POST /auth", "POST /screen/backtest"]
    authentication, request = server.received
    assert "authorization" not in authentication.headers
    assert json.loads(authentication.body) == {
        "apiId": canaries.API_ID,
        "apiKey": canaries.API_KEY,
    }
    # The .netrc login would have replaced the bearer token.
    assert request.headers["authorization"] == f"Bearer {canaries.TOKEN}"
