"""The start record, `started.json`, and the attempt record, `attempt.json`, schema version 1.0.0
(docs/contracts.md, execution outcomes and attempts).
"""

from typing import Annotated, Literal, Self

from pydantic import UUID4, Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    CaseId,
    ContractModel,
    ErrorDetail,
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

    @model_validator(mode="after")
    def _status_with_response(self) -> Self:
        if (self.status is None) == (self.result == "response"):
            raise ValueError("status must be given exactly when the result is response")
        return self


class _AttemptIdentity(ContractModel):
    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    attempt_id: UUID4
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

    exchanges: tuple[Exchange, ...]
    """The exchanges completed before it: Trial Folio's authentication call, when the attempt
    started with one."""


class ArtifactReference(ContractModel):
    """A file in the output directory, by path and content address."""

    path: RelativePath
    artifact_id: Sha256Digest


class SavedResponse(ArtifactReference):
    """The saved response: `response.json`, the decoded payload, or `response.raw`, the body of a
    200 the wrapper couldn't decode."""

    form: Literal["decoded", "undecoded"]


class ProviderMetadata(ContractModel):
    """What the provider reported about the charge: `cost` and `quotaRemaining`. Each is null when
    the response doesn't carry it."""

    cost: Annotated[int, Field(ge=0)] | None
    quota_remaining: Annotated[int, Field(ge=0)] | None
    """`quotaRemaining`: account information, kept out of shareable outputs."""


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
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not be before started_at")
        if (self.error is None) != (self.outcome == "succeeded"):
            raise ValueError("error must be given exactly when the outcome isn't succeeded")
        if self.outcome == "succeeded" and self.response is None:
            raise ValueError("a succeeded attempt must reference its saved response")
        sent = any(
            exchange.result != "not_connected"
            for exchange in self.exchanges
            if exchange.request != AUTHENTICATION_REQUEST
        )
        if self.possibly_charged != sent:
            raise ValueError(
                "possibly_charged must be true exactly when a send of the request may have "
                "reached Portfolio123: an exchange other than authentication that isn't "
                "not_connected"
            )
        if self.outcome == "unknown" and not self.possibly_charged:
            raise ValueError("an unknown attempt is possibly charged")
        return self
