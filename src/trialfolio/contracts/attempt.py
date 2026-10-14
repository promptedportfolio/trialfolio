"""The start record, `started.json`, and the attempt record, `attempt.json` (docs/contracts.md,
execution outcomes and attempts): version 1.0.0, a screen run's, and version 1.1.0, an
experiment's, with the authentication record, `authenticating.json` (experiment attempts); and,
from 0.4.0, versions 1.2.0, a screen run's and a ranking snapshot's, and 1.3.0, an experiment's,
for an attempt that sends a ranking definition (sending a definition).

A run of an experiment authenticates once, and again only after a 401 or 403, so an experiment's
attempt may send with a token an earlier attempt of the same session obtained. Version 1.1.0
names the attempt whose authentication it used, `authenticated_by`, its `session` and its place
in it, `sequence`, and the attempt a repeat repeats, `repeat_of`. Whether those attempts exist,
and authenticated, is the records check's to say, on resume: a model sees one record.

An attempt that sends a definition makes two requests, its `rank_update`, then its backtest, so
each of its start records names its request's `operation`: the update record, `updating.json`,
before the `rank_update`, and `started.json` before the backtest. Its attempt record adds the
`rank_update`'s files and provider metadata, in `ranking_update`. A snapshot's attempt writes
records 1.2.0 too, with the one request `rank_get`, and no case.
"""

from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    RANK_GET_REQUEST,
    RANK_UPDATE_REQUEST,
    SCREEN_BACKTEST_REQUEST,
    AttemptId,
    CaseId,
    ContractModel,
    ErrorDetail,
    Ordinal,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
    TransportVersions,
    UtcDatetime,
    WrapperVersions,
)


class Exchange(ContractModel):
    """One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP
    exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.
    """

    request: Annotated[str, StringConstraints(pattern=r"^[A-Z]+ /[^\s]*$")]
    """The method and path, such as `POST /auth` or `POST /screen/backtest`."""
    result: Literal["response", "not_connected", "interrupted"]
    status: Annotated[int, Field(ge=100, le=599)] | None
    """The HTTP status of a `response`; null otherwise."""
    note: Literal["completed_from_saved_response"] | None
    """Set only on a restarted attempt's request exchange, recorded as a 200 because its response
    was found saved (uncertain completion); null otherwise."""

    @model_validator(mode="after")
    def _status_with_response(self) -> Self:
        if (self.status is None) == (self.result == "response"):
            raise ValueError("status must be given exactly when the result is response")
        if self.note is not None and self.status != 200:
            raise ValueError("only a 200 response can be completed from a saved response")
        return self


class _AttemptIdentity(ContractModel):
    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions


class StartRecord(_AttemptIdentity):
    """The start record, written durably just before the request is sent. Without an attempt
    record beside it, the attempt is `running` (uncertain completion).
    """

    exchanges: tuple[Exchange]
    """The successful authentication exchange completed before the request in 0.1.0."""

    @model_validator(mode="after")
    def _authentication_only(self) -> Self:
        # It's written before the request is sent, so only authentication can precede it.
        (authentication,) = self.exchanges
        if authentication.request != AUTHENTICATION_REQUEST:
            raise ValueError("a start record holds only the authentication exchange")
        if authentication.status != 200:
            raise ValueError("a start record requires successful authentication")
        if authentication.note is not None:
            raise ValueError("a start record's exchange carries no note")
        return self


class ArtifactReference(ContractModel):
    """A file in the output directory, by path and content address."""

    path: RelativePath
    artifact_id: Sha256Digest


class SavedResponse(ArtifactReference):
    """The saved response: `response.json`, the decoded payload, or `response.raw`, the body of a
    200 the wrapper couldn't decode."""

    form: Literal["decoded", "undecoded"]

    @model_validator(mode="after")
    def _form_matches_file(self) -> Self:
        expected = "response.json" if self.form == "decoded" else "response.raw"
        if self.path.rsplit("/", 1)[-1] != expected:
            raise ValueError(f"a response of form {self.form} is saved as {expected}")
        return self


class ProviderMetadata(ContractModel):
    """What the provider reported about the charge: `cost` and `quotaRemaining`. Each is null when
    the response doesn't carry it."""

    cost: Annotated[int, Field(ge=0)] | None
    quota_remaining: Annotated[int, Field(ge=0)] | None
    """`quotaRemaining`: account information, kept out of shareable outputs."""


def _outcomes_of(send: Exchange | None, *, saved: bool) -> set[str]:
    """The outcomes the request's exchange allows, as 0.1.0's failure table gives them."""
    if send is None:
        # Never sent; or, for a restart without a saved response, unknown.
        return {"failed", "unknown"}
    if send.result == "not_connected":
        return {"failed"}
    if send.result == "interrupted" or (send.status is not None and send.status >= 500):
        return {"unknown"}
    if send.status == 200:
        return {"succeeded"} if saved else {"unknown"}
    return {"failed"}


class AttemptRecord(_AttemptIdentity):
    """The attempt record, written once when the attempt ends: everything in the start record,
    plus how the attempt ended.
    """

    ended_at: UtcDatetime
    outcome: Literal["succeeded", "failed", "unknown"]
    error: ErrorDetail | None
    """Null exactly when the outcome is `succeeded`."""
    exchanges: tuple[Exchange, ...]
    """Every exchange, in order."""
    possibly_charged: bool
    """True when a send of the request may have reached Portfolio123 (possibly charged)."""
    request: ArtifactReference | None
    """The redacted request, `request.json`."""
    response: SavedResponse | None
    provider_metadata: ProviderMetadata

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        sends, authentication = check_ending(self)
        if (sends or self.outcome == "unknown") and (
            not authentication or authentication[0].status != 200
        ):
            raise ValueError("sending or restarting a request requires successful authentication")
        return self


class _Ending(Protocol):
    """What `check_ending` reads of an attempt record, of either version."""

    @property
    def started_at(self) -> datetime: ...
    @property
    def ended_at(self) -> datetime: ...
    @property
    def outcome(self) -> Literal["succeeded", "failed", "unknown"]: ...
    @property
    def error(self) -> ErrorDetail | None: ...
    @property
    def exchanges(self) -> tuple[Exchange, ...]: ...
    @property
    def possibly_charged(self) -> bool: ...
    @property
    def request(self) -> ArtifactReference | None: ...
    @property
    def response(self) -> SavedResponse | None: ...


def check_ending(record: _Ending) -> tuple[list[Exchange], list[Exchange]]:
    """Raises `ValueError` unless the attempt record's ending is consistent, by the rules both
    versions share: its outcome, error, files, and `possibly_charged` follow its exchanges, as
    0.1.0's failure table gives them. Returns its request's exchanges and its authentication
    exchanges, for the rule of its version."""
    if record.ended_at < record.started_at:
        raise ValueError("ended_at must not be before started_at")
    if (record.error is None) != (record.outcome == "succeeded"):
        raise ValueError("error must be given exactly when the outcome isn't succeeded")
    if record.request is not None and record.request.path.rsplit("/", 1)[-1] != "request.json":
        raise ValueError("the redacted request is saved as request.json")
    if (record.response is not None) != (record.outcome == "succeeded"):
        raise ValueError("a response is saved exactly when the attempt succeeded")
    sends = [e for e in record.exchanges if e.request != AUTHENTICATION_REQUEST]
    if len(sends) > 1:
        raise ValueError("the request is sent at most once, so it has at most one exchange")
    authentication = [e for e in record.exchanges if e.request == AUTHENTICATION_REQUEST]
    if len(authentication) > 1:
        raise ValueError("an attempt has at most one authentication exchange")
    if authentication and record.exchanges[0] != authentication[0]:
        raise ValueError("authentication must precede the request")
    if sends and record.request is None:
        raise ValueError("a request exchange requires its saved request reference")
    if any(e.note is not None for e in authentication):
        raise ValueError("only the request's exchange can carry a note")
    if any(e.note is not None for e in sends) and record.outcome != "succeeded":
        raise ValueError("a note marks a restarted attempt that succeeded")
    outcomes = _outcomes_of(sends[0] if sends else None, saved=record.response is not None)
    if record.outcome not in outcomes:
        raise ValueError(
            f"the request's exchange makes the outcome {' or '.join(sorted(outcomes))}"
        )
    # An unknown attempt restarted without a saved response has no request exchange in its
    # start record, and is still possibly charged (uncertain completion).
    sent = any(e.result != "not_connected" for e in sends) or record.outcome == "unknown"
    if record.possibly_charged != sent:
        raise ValueError(
            "possibly_charged must be true exactly when the attempt is unknown, or a send of "
            "the request may have reached Portfolio123: an exchange other than "
            "authentication that isn't not_connected"
        )
    return sends, authentication


# Version 1.1.0, an experiment's.


class AuthenticationRecord(ContractModel):
    """The authentication record, `authenticating.json`, written durably before an experiment's
    attempt makes Trial Folio's own authentication call, so the budget counts the call even when
    the process is killed before its exchange is recorded (experiment attempts). An attempt
    that sends with a token its session already holds has none."""

    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    session: Ordinal
    """The number of the session that started the attempt."""
    sequence: Ordinal
    """The attempt's place in its session: 1 for the first attempt it starts."""
    repeat_of: AttemptId | None
    """The attempt that `--repeat`'s confirmation named, for an attempt it started; null for any
    other."""
    started_at: UtcDatetime

    @model_validator(mode="after")
    def _not_its_own_repeat(self) -> Self:
        if self.repeat_of == self.attempt_id:
            raise ValueError("an attempt doesn't repeat itself")
        return self


class _ExperimentAttemptIdentity(ContractModel):
    schema_version: Literal["1.1.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    session: Ordinal
    """The number of the session that started the attempt."""
    sequence: Ordinal
    """The attempt's place in its session: 1 for the first attempt it starts. It orders a
    session's attempts, which their start times can't, because the clock can move backward."""


class StartRecordV1_1(_ExperimentAttemptIdentity):
    """An experiment's start record, written durably just before the request is sent. Without
    an attempt record beside it, the attempt is `running` (uncertain completion)."""

    authenticated_by: AttemptId
    """The attempt whose successful authentication gave the token the request is sent with: this
    one, or an earlier one of its session."""
    repeat_of: AttemptId | None
    """The attempt that `--repeat`'s confirmation named, for an attempt it started; null for any
    other."""
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    exchanges: Annotated[tuple[Exchange, ...], Field(max_length=1)]
    """The exchange completed before the send: Trial Folio's successful authentication call, or
    none when the session already held a token."""

    @model_validator(mode="after")
    def _authenticated(self) -> Self:
        if self.repeat_of == self.attempt_id:
            raise ValueError("an attempt doesn't repeat itself")
        if not self.exchanges:
            if self.authenticated_by == self.attempt_id:
                raise ValueError("an attempt that authenticated has its authentication exchange")
            return self
        (authentication,) = self.exchanges
        if authentication.request != AUTHENTICATION_REQUEST:
            raise ValueError("a start record holds only the authentication exchange")
        if authentication.status != 200:
            raise ValueError("a start record requires successful authentication")
        if authentication.note is not None:
            raise ValueError("a start record's exchange carries no note")
        if self.authenticated_by != self.attempt_id:
            raise ValueError("an attempt that authenticates sends with its own token")
        return self


class AttemptRecordV1_1(_ExperimentAttemptIdentity):
    """An experiment's attempt record, written once when the attempt ends: everything in its
    start record, when it has one, plus how the attempt ended."""

    authenticated_by: AttemptId | None
    """As in the start record, given exactly when the attempt has one."""
    repeat_of: AttemptId | None
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    ended_at: UtcDatetime
    outcome: Literal["succeeded", "failed", "unknown"]
    error: ErrorDetail | None
    """Null exactly when the outcome is `succeeded`."""
    exchanges: tuple[Exchange, ...]
    """Every exchange of this attempt, in order. It has no authentication exchange when it sent
    with an earlier attempt's token."""
    possibly_charged: bool
    request: ArtifactReference | None
    response: SavedResponse | None
    provider_metadata: ProviderMetadata

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.repeat_of == self.attempt_id:
            raise ValueError("an attempt doesn't repeat itself")
        sends, authentication = check_ending(self)
        own = self.authenticated_by == self.attempt_id
        if own and (not authentication or authentication[0].status != 200):
            raise ValueError("an attempt that sends with its own token authenticated successfully")
        if authentication and self.authenticated_by not in (None, self.attempt_id):
            raise ValueError("an attempt that authenticates sends with its own token")
        if (sends or self.outcome == "unknown") and self.authenticated_by is None:
            raise ValueError(
                "sending or restarting a request requires successful authentication in its "
                "session, named by authenticated_by"
            )
        return self


# Versions 1.2.0 and 1.3.0: an attempt that sends a definition, and a snapshot's.

RankingOperation = Literal["rank_update", "screen_backtest", "rank_get"]
"""The request a start record comes before: a case's `rank_update` or its backtest, or a
snapshot's `rank_get`."""


def _successful_authentication(exchange: Exchange) -> None:
    if exchange.request != AUTHENTICATION_REQUEST:
        raise ValueError("a start record holds the authentication exchange first")
    if exchange.status != 200:
        raise ValueError("a start record requires successful authentication")


def _check_start_exchanges(
    operation: RankingOperation, exchanges: tuple[Exchange, ...], *, authenticated: bool
) -> None:
    """Raises `ValueError` unless a start record's exchanges are those completed before its send:
    Trial Folio's successful authentication, when `authenticated`, and, before a backtest, the
    `rank_update`'s exchange, a 200 (sending a definition)."""
    expected = (1 if authenticated else 0) + (1 if operation == "screen_backtest" else 0)
    if len(exchanges) != expected:
        raise ValueError(
            "a start record holds the exchanges completed before its send: its authentication's, "
            "and before a backtest, its rank_update's"
        )
    if any(exchange.note is not None for exchange in exchanges):
        raise ValueError("a start record's exchanges carry no note")
    if authenticated:
        _successful_authentication(exchanges[0])
    if operation == "screen_backtest":
        update = exchanges[-1]
        if update.request != RANK_UPDATE_REQUEST or update.status != 200:
            raise ValueError("a backtest's start record follows its rank_update's 200")


class StartRecordV1_2(ContractModel):
    """A start record 1.2.0: a screen run's attempt that sends a definition, or a snapshot's.
    It's written durably just before its send: the update record, `updating.json`, before the
    `rank_update`, and `started.json` before the backtest, or before a snapshot's `rank_get`."""

    schema_version: Literal["1.2.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId | None
    """The case; null for a snapshot's attempt, which plans no case."""
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    operation: RankingOperation
    """The request it comes before."""
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    exchanges: tuple[Exchange, ...]
    """Trial Folio's successful authentication, and in `started.json` before a backtest, the
    `rank_update`'s exchange, `POST /rank` with a 200."""

    @model_validator(mode="after")
    def _before_its_send(self) -> Self:
        if (self.case_id is None) != (self.operation == "rank_get"):
            raise ValueError("a snapshot's attempt, and only a snapshot's, has no case")
        # A screen run's attempt, and a snapshot's, always authenticates first.
        _check_start_exchanges(self.operation, self.exchanges, authenticated=True)
        return self


class StartRecordV1_3(ContractModel):
    """A start record 1.3.0: an experiment's attempt that sends a definition. The update record,
    `updating.json`, comes before its `rank_update`, and `started.json` before its backtest. The
    two hold the same values in every field but `operation` and `exchanges`."""

    schema_version: Literal["1.3.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    session: Ordinal
    """The number of the session that started the attempt."""
    sequence: Ordinal
    """The attempt's place in its session: 1 for the first attempt it starts."""
    operation: Literal["rank_update", "screen_backtest"]
    """The request it comes before."""
    authenticated_by: AttemptId
    """The attempt whose successful authentication gave the token the requests are sent with:
    this one, or an earlier one of its session."""
    repeat_of: AttemptId | None
    """The attempt that `--repeat`'s confirmation named, for an attempt it started; null for any
    other."""
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    exchanges: tuple[Exchange, ...]
    """Trial Folio's successful authentication, or none when the session already held a token;
    and in `started.json`, the `rank_update`'s exchange, `POST /rank` with a 200."""

    @model_validator(mode="after")
    def _before_its_send(self) -> Self:
        if self.repeat_of == self.attempt_id:
            raise ValueError("an attempt doesn't repeat itself")
        authenticated = bool(self.exchanges) and self.exchanges[0].request == AUTHENTICATION_REQUEST
        _check_start_exchanges(self.operation, self.exchanges, authenticated=authenticated)
        if authenticated != (self.authenticated_by == self.attempt_id):
            raise ValueError(
                "an attempt that authenticates sends with its own token, and holds its "
                "authentication exchange"
            )
        return self


class RankUpdateResponse(ArtifactReference):
    """The `rank_update`'s saved response: `rank-update-response.json`, the decoded payload, or
    `rank-update-response.raw`, the body of a 200 the wrapper couldn't decode."""

    form: Literal["decoded", "undecoded"]

    @model_validator(mode="after")
    def _form_matches_file(self) -> Self:
        expected = "rank-update-response." + ("json" if self.form == "decoded" else "raw")
        if self.path.rsplit("/", 1)[-1] != expected:
            raise ValueError(f"a rank_update response of form {self.form} is saved as {expected}")
        return self


class RankingUpdate(ContractModel):
    """The `rank_update` an attempt sent before its backtest: its request, its saved response,
    and what Portfolio123 reported of its charge (sending a definition)."""

    request: ArtifactReference | None
    """`rank-update-request.json`; null when the attempt ended before writing it."""
    response: RankUpdateResponse | None
    """The saved response; null when none was saved."""
    provider_metadata: ProviderMetadata
    """The `cost` and `quotaRemaining` of its decoded response, each null when it doesn't carry
    it."""

    @model_validator(mode="after")
    def _request_file(self) -> Self:
        if self.request is not None and self.request.path.rsplit("/", 1)[-1] != (
            "rank-update-request.json"
        ):
            raise ValueError("a rank_update's request is saved as rank-update-request.json")
        return self


class _RankingEnding(Protocol):
    """What `check_ranking_ending` reads of an attempt record 1.2.0 or 1.3.0."""

    @property
    def started_at(self) -> datetime: ...
    @property
    def ended_at(self) -> datetime: ...
    @property
    def operation(self) -> RankingOperation: ...
    @property
    def outcome(self) -> Literal["succeeded", "failed", "unknown"]: ...
    @property
    def error(self) -> ErrorDetail | None: ...
    @property
    def exchanges(self) -> tuple[Exchange, ...]: ...
    @property
    def possibly_charged(self) -> bool: ...
    @property
    def ranking_update(self) -> RankingUpdate | None: ...
    @property
    def request(self) -> ArtifactReference | None: ...
    @property
    def response(self) -> SavedResponse | None: ...


def check_ranking_ending(record: _RankingEnding) -> list[Exchange]:
    """Raises `ValueError` unless an attempt record 1.2.0's or 1.3.0's ending is consistent, as
    sending a definition gives it: a snapshot's `rank_get` by 0.1.0's rules; and an attempt with a
    definition's exchanges in order, its authentication's, then `POST /rank`, then
    `POST /screen/backtest`, each at most once, with its outcome, error, files, and
    `possibly_charged` following them. Returns its exchanges other than authentication's."""
    if record.operation == "rank_get":
        if record.ranking_update is not None:
            raise ValueError("a snapshot's attempt sends no rank_update")
        sends, _ = check_ending(record)
        if any(exchange.request != RANK_GET_REQUEST for exchange in sends):
            raise ValueError("a snapshot's attempt sends one GET /rank, and nothing else")
        return sends
    update = record.ranking_update
    if update is None:
        raise ValueError("an attempt that sends a definition records its rank_update")
    if record.ended_at < record.started_at:
        raise ValueError("ended_at must not be before started_at")
    if (record.error is None) != (record.outcome == "succeeded"):
        raise ValueError("error must be given exactly when the outcome isn't succeeded")
    if record.request is not None and record.request.path.rsplit("/", 1)[-1] != "request.json":
        raise ValueError("the backtest's redacted request is saved as request.json")
    if (record.response is not None) != (record.outcome == "succeeded"):
        raise ValueError("the backtest's response is saved exactly when the attempt succeeded")
    order = (AUTHENTICATION_REQUEST, RANK_UPDATE_REQUEST, SCREEN_BACKTEST_REQUEST)
    if any(exchange.request not in order for exchange in record.exchanges):
        raise ValueError("an attempt that sends a definition sends POST /rank, then its backtest")
    positions = [order.index(e.request) for e in record.exchanges if e.request in order]
    if positions != sorted(set(positions)):
        raise ValueError(
            "an attempt's exchanges come in order, each at most once: its authentication's, "
            "then POST /rank, then POST /screen/backtest"
        )
    found = {exchange.request: exchange for exchange in record.exchanges}
    authentication = found.get(AUTHENTICATION_REQUEST)
    rank, backtest = found.get(RANK_UPDATE_REQUEST), found.get(SCREEN_BACKTEST_REQUEST)
    if authentication is not None and authentication.note is not None:
        raise ValueError("only a request's exchange can carry a note")
    _check_rank_update(update, rank, backtest)
    if backtest is not None and record.request is None:
        raise ValueError("a backtest's exchange requires its saved request reference")
    if backtest is not None and backtest.note is not None and record.outcome != "succeeded":
        raise ValueError("a note on the backtest marks a restarted attempt that succeeded")
    if rank is not None and rank.note is not None and record.outcome != "failed":
        raise ValueError(
            "a note on the rank_update marks an attempt a resume recorded as failed, from its "
            "update record and the rank_update's saved response"
        )
    outcomes = _ranking_outcomes(rank, backtest, saved=record.response is not None)
    if record.outcome not in outcomes:
        raise ValueError(f"the exchanges make the outcome {' or '.join(sorted(outcomes))}")
    sends = [exchange for exchange in (rank, backtest) if exchange is not None]
    sent = any(e.result != "not_connected" for e in sends) or record.outcome == "unknown"
    if record.possibly_charged != sent:
        raise ValueError(
            "possibly_charged must be true exactly when the attempt is unknown, or a send of its "
            "rank_update or its backtest may have reached Portfolio123"
        )
    return sends


def _check_rank_update(
    update: RankingUpdate, rank: Exchange | None, backtest: Exchange | None
) -> None:
    """Raises `ValueError` unless the `rank_update`'s files follow its exchange, and a backtest
    follows only a `rank_update` that got a 200 the wrapper decoded, whose response was saved."""
    if rank is not None and update.request is None:
        raise ValueError("a rank_update's exchange requires its saved request reference")
    if update.response is not None and (rank is None or rank.status != 200):
        raise ValueError("a rank_update's response is saved only after its 200")
    if rank is not None and rank.note is not None and backtest is not None:
        raise ValueError(
            "a note on the rank_update marks an attempt a resume recorded from its update record, "
            "which sent no backtest"
        )
    if backtest is not None and (
        rank is None
        or rank.status != 200
        or update.response is None
        or update.response.form != "decoded"
    ):
        raise ValueError(
            "a backtest is sent only after its rank_update got a 200 the wrapper decoded, and "
            "its response was saved"
        )


def _ranking_outcomes(rank: Exchange | None, backtest: Exchange | None, *, saved: bool) -> set[str]:
    """The outcomes an attempt that sends a definition allows: the backtest's exchange gives it,
    as the request's does in 1.0.0. Without one, the backtest wasn't sent, or a resume recorded the
    attempt from `started.json` without a saved response, which is `unknown`; and without a 200 to
    its `rank_update`, the attempt is `unknown` when the write may or may not have taken effect,
    and `failed` otherwise, with no `rank_update` exchange included."""
    if backtest is not None:
        return _outcomes_of(backtest, saved=saved)
    if rank is None or rank.result == "not_connected":
        return {"failed"}
    if rank.result == "interrupted" or (rank.status is not None and rank.status >= 500):
        return {"unknown"}
    if rank.status == 200:
        return {"failed", "unknown"}
    return {"failed"}


class AttemptRecordV1_2(ContractModel):
    """An attempt record 1.2.0: a screen run's attempt that sends a definition, or a snapshot's,
    written once when the attempt ends: its start record's fields, how it ended, and, for a
    definition, its `rank_update`."""

    schema_version: Literal["1.2.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId | None
    """The case; null for a snapshot's attempt."""
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    operation: Literal["screen_backtest", "rank_get"]
    """The attempt's last request: the backtest, or a snapshot's `rank_get`."""
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    ended_at: UtcDatetime
    outcome: Literal["succeeded", "failed", "unknown"]
    error: ErrorDetail | None
    """Null exactly when the outcome is `succeeded`."""
    exchanges: tuple[Exchange, ...]
    """Every exchange, in order: the authentication's, then `POST /rank`, then
    `POST /screen/backtest`; or a snapshot's authentication and `GET /rank`."""
    possibly_charged: bool
    ranking_update: RankingUpdate | None
    """The `rank_update`'s request, response, and provider metadata; null for a snapshot's."""
    request: ArtifactReference | None
    """The backtest's, or the `rank_get`'s, redacted request, `request.json`."""
    response: SavedResponse | None
    provider_metadata: ProviderMetadata
    """The backtest's, or the `rank_get`'s."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.case_id is None) != (self.operation == "rank_get"):
            raise ValueError("a snapshot's attempt, and only a snapshot's, has no case")
        # Either version's ending puts its one authentication exchange, if any, first.
        sends = check_ranking_ending(self)
        first = self.exchanges[0] if self.exchanges else None
        authenticated = (
            first is not None and first.request == AUTHENTICATION_REQUEST and first.status == 200
        )
        if (sends or self.outcome == "unknown") and not authenticated:
            raise ValueError("sending or restarting a request requires successful authentication")
        return self


class AttemptRecordV1_3(ContractModel):
    """An attempt record 1.3.0: an experiment's attempt that sends a definition, written once
    when it ends: 1.1.0's fields, with its `operation` and its `rank_update`."""

    schema_version: Literal["1.3.0"]
    trialfolio_version: SemanticVersion
    attempt_id: AttemptId
    case_id: CaseId
    plan_hash: Sha256Digest
    """The plan the attempt runs under."""
    session: Ordinal
    """The number of the session that started the attempt."""
    sequence: Ordinal
    """The attempt's place in its session."""
    operation: Literal["screen_backtest"]
    """The attempt's last request, its backtest."""
    authenticated_by: AttemptId | None
    """As in its start records, given exactly when it has one."""
    repeat_of: AttemptId | None
    started_at: UtcDatetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    ended_at: UtcDatetime
    outcome: Literal["succeeded", "failed", "unknown"]
    error: ErrorDetail | None
    """Null exactly when the outcome is `succeeded`."""
    exchanges: tuple[Exchange, ...]
    """Every exchange of this attempt, in order. It has no authentication exchange when it sent
    with an earlier attempt's token."""
    possibly_charged: bool
    ranking_update: RankingUpdate
    """The `rank_update`'s request, response, and provider metadata."""
    request: ArtifactReference | None
    """The backtest's redacted request, `request.json`."""
    response: SavedResponse | None
    provider_metadata: ProviderMetadata
    """The backtest's."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.repeat_of == self.attempt_id:
            raise ValueError("an attempt doesn't repeat itself")
        sends = check_ranking_ending(self)
        authentication = [e for e in self.exchanges if e.request == AUTHENTICATION_REQUEST]
        own = self.authenticated_by == self.attempt_id
        if own and (not authentication or authentication[0].status != 200):
            raise ValueError("an attempt that sends with its own token authenticated successfully")
        if authentication and self.authenticated_by not in (None, self.attempt_id):
            raise ValueError("an attempt that authenticates sends with its own token")
        if (sends or self.outcome == "unknown") and self.authenticated_by is None:
            raise ValueError(
                "sending or restarting a request requires successful authentication in its "
                "session, named by authenticated_by"
            )
        return self
