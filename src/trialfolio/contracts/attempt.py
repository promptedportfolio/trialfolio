"""The start record, `started.json`, and the attempt record, `attempt.json`, schema version 1.0.0
(docs/contracts.md, execution outcomes and attempts).
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    AttemptId,
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

    exchanges: tuple[Exchange, ...]
    """The exchanges completed before it: Trial Folio's authentication call, when the attempt
    started with one."""

    @model_validator(mode="after")
    def _no_notes(self) -> Self:
        if any(exchange.note is not None for exchange in self.exchanges):
            raise ValueError("a start record's exchanges carry no note")
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
        if self.request is not None and self.request.path.rsplit("/", 1)[-1] != "request.json":
            raise ValueError("the redacted request is saved as request.json")
        sends = [e for e in self.exchanges if e.request != AUTHENTICATION_REQUEST]
        if self.outcome == "succeeded" and (
            self.response is None or not any(e.status == 200 for e in sends)
        ):
            raise ValueError("a succeeded attempt has a 200 response, saved and referenced")
        # An unknown attempt restarted without a saved response has no request exchange in its
        # start record, and is still possibly charged (uncertain completion).
        sent = any(e.result != "not_connected" for e in sends) or self.outcome == "unknown"
        if self.possibly_charged != sent:
            raise ValueError(
                "possibly_charged must be true exactly when the attempt is unknown, or a send of "
                "the request may have reached Portfolio123: an exchange other than "
                "authentication that isn't not_connected"
            )
        return self
