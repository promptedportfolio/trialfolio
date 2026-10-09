"""The start record, `started.json`, and the attempt record, `attempt.json` (docs/contracts.md,
execution outcomes and attempts): version 1.0.0, a screen run's, and version 1.1.0, an
experiment's, with the authentication record, `authenticating.json` (experiment attempts).

A run of an experiment authenticates once, and again only after a 401 or 403, so an experiment's
attempt may send with a token an earlier attempt of the same session obtained. Version 1.1.0
names the attempt whose authentication it used, `authenticated_by`, its `session` and its place
in it, `sequence`, and the attempt a repeat repeats, `repeat_of`. Whether those attempts exist,
and authenticated, is the records check's to say, on resume: a model sees one record.
"""

from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
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
