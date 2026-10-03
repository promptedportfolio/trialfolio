"""The client keeps credential objects contained, and keeps only a sanitized message from the
wrapper's errors.

Traces to docs/contracts.md, credentials (REQ-09, INV-11): credential objects are never
serialized or logged, and from an error Trial Folio keeps only the status and a sanitized message.
To ADR 0001, decision 7, and docs/contracts.md, logging (INV-14): logs hold no credentials,
tokens, or provider text. And to HTTP exchanges: Trial Folio authenticates with its own call
before a request.
"""

import copy
import logging
import pickle

import pytest

from tests.provider.conftest import PARAMS, authenticate
from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.errors import TrialFolioError
from trialfolio.provider import Credentials, P123ScreenBacktestClient, ProviderError


def test_credentials_never_show_or_serialize_their_values() -> None:
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)

    assert canaries.API_ID not in repr(credentials)
    assert canaries.API_KEY not in repr(credentials)
    with pytest.raises(TypeError):
        pickle.dumps(credentials)
    with pytest.raises(TypeError):
        copy.copy(credentials)


@pytest.mark.parametrize(("api_id", "api_key"), [("", canaries.API_KEY), (canaries.API_ID, " ")])
def test_blank_credentials_fail_authentication_before_any_request(
    api_id: str, api_key: str
) -> None:
    with pytest.raises(TrialFolioError) as raised:
        Credentials(api_id, api_key)

    assert raised.value.code == "provider.auth_failed"
    assert "DataMiner & API" in raised.value.message


def test_a_request_needs_trial_folios_own_authentication_first(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    # Otherwise the wrapper would authenticate inside the request's call.
    with pytest.raises(RuntimeError):
        client.screen_backtest(PARAMS)

    assert client.exchanges == ()
    assert server.requests() == []


def test_portfolio123s_message_is_sanitized(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    authenticate(server, client)
    text = (
        f"Bad\x1b[31m value\r\n\tfor {canaries.API_ID} {canaries.API_KEY} {canaries.TOKEN} "
        + "x" * 400
    )
    server.reply("/screen/backtest", Reply(400, text.encode()))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    message = raised.value.provider_message
    assert message is not None
    assert message.startswith("Bad [31m value for [redacted] [redacted] [redacted] xxx")
    assert len(message) == 300
    assert message.endswith("x…")
    for secret in (canaries.API_ID, canaries.API_KEY, canaries.TOKEN, "\x1b", "\n", "\t"):
        assert secret not in raised.value.message


def test_errors_carry_no_reference_to_the_wrappers_exception(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    # The wrapper's exception holds the response, whose request carries the bearer token.
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(400, b"Invalid parameter"))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__traceback__ is not None
    frames = []
    traceback = raised.value.__traceback__
    while traceback is not None:
        frames.append(traceback.tb_frame.f_code.co_name)
        traceback = traceback.tb_next
    # Raised by the client itself, outside the wrapper's frames.
    assert frames[-1] == "screen_backtest"


def test_a_provider_error_keeps_its_parts_when_copied() -> None:
    error = ProviderError("provider.unsupported_capability", "Rejected.", "Invalid parameter")

    copied = pickle.loads(pickle.dumps(error))

    assert (copied.code, copied.message, copied.log_message, copied.provider_message) == (
        error.code,
        error.message,
        "Rejected.",
        "Invalid parameter",
    )


def test_logs_hold_no_credentials_tokens_parameters_or_provider_text(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(400, b"canary-provider-text"))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    records = [record for record in caplog.records if record.name.startswith("trialfolio")]
    events = [getattr(record, "event", None) for record in records]
    assert events == [
        "provider.request.started",
        "provider.request.completed",
        "provider.request.started",
        "provider.request.completed",
    ]
    logged = "\n".join(record.getMessage() for record in records)
    for canary in (canaries.API_ID, canaries.API_KEY, canaries.TOKEN, "canary-provider-text"):
        assert canary not in logged
    assert "SP500" not in logged
    # The provider's text is in the message, for the terminal, and not in the loggable one.
    assert "canary-provider-text" in raised.value.message
    assert "canary-provider-text" not in raised.value.log_message


def test_a_refused_exchange_is_logged(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(401))

    with pytest.raises(ProviderError):
        client.screen_backtest(PARAMS)

    refused = [r for r in caplog.records if getattr(r, "event", None) == "provider.request.refused"]
    assert [r.levelno for r in refused] == [logging.WARNING]
