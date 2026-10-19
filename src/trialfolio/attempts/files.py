"""An attempt's files (docs/contracts.md, execution outcomes and attempts): their names, their
roles in a manifest, the directory that holds them, and `AttemptFiles`, the file writer, which
writes each file once, never replacing one, and lists every file the attempt wrote.

- **`request.json`** is `json.dumps` of the `params` sent, indented. `requests` writes the body
  with the same function, unindented, so each number's text is the body's. Non-ASCII text is
  escaped, as in the body.
- **`response.json`** is `json.dumps` of the decoded value, on one line. Unindented, `json` uses
  its C encoder, which nests as deep as the C decoder that read the value; the Python encoder
  that indenting uses could run out of recursion first. Non-ASCII text is escaped, so a lone
  surrogate the decoder accepted is written back as it came. So are `NaN` and `Infinity`.
- **`provider_metadata`** takes `cost` and `quotaRemaining` from the top level of a decoded
  response. Each is null when it's absent or isn't a non-negative integer.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal, cast

from pydantic import BaseModel

from trialfolio.contracts.attempt import (
    ArtifactReference,
    ProviderMetadata,
    RankingUpdate,
    RankUpdateResponse,
    SavedResponse,
)
from trialfolio.manifests import model_json
from trialfolio.provider import DecodedResponse, ScreenBacktestResponse, UndecodedResponse
from trialfolio.storage import ArtifactStore, StoredFile, published

AUTHENTICATION_RECORD: Final = "authenticating.json"
UPDATE_RECORD: Final = "updating.json"
START_RECORD: Final = "started.json"
ATTEMPT_RECORD: Final = "attempt.json"
RANK_UPDATE_REQUEST_FILE: Final = "rank-update-request.json"
RANK_UPDATE_RESPONSE_FILE: Final = "rank-update-response.json"
RANK_UPDATE_RESPONSE_RAW: Final = "rank-update-response.raw"

type AttemptRole = Literal[
    "authentication_record",
    "rank_update_request",
    "update_record",
    "rank_update_response",
    "rank_update_response_undecoded",
    "start_record",
    "attempt_record",
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
]
"""The role of each file an attempt writes, as a manifest lists it. Only an experiment's attempts
write an authentication record, and only an attempt that sends a definition the `rank_update`'s
files."""


def attempt_directory(case_id: str, attempt_id: uuid.UUID) -> str:
    """`cases/<case_id>/attempts/<attempt_id>`, relative to the output root."""
    return f"cases/{case_id}/attempts/{attempt_id}"


def snapshot_attempt_directory(attempt_id: uuid.UUID) -> str:
    """A ranking snapshot's `attempts/<attempt_id>`, relative to its directory: it plans no
    case."""
    return f"attempts/{attempt_id}"


@dataclass(frozen=True)
class AttemptFile:
    """A file an attempt wrote, with its role in the manifest."""

    role: AttemptRole
    file: StoredFile


class AttemptFiles:
    """An attempt's directory, `cases/<case_id>/attempts/<attempt_id>/`, or a snapshot's
    `attempts/<attempt_id>/`, for any version of its records: it writes each file once, never
    replacing one, and saves the responses, keeping what the attempt record references."""

    def __init__(self, store: ArtifactStore, directory: str) -> None:
        self._store = store
        self._directory = directory
        self._files: list[AttemptFile] = []
        self.request: StoredFile | None = None
        self.response: tuple[StoredFile, ScreenBacktestResponse] | None = None
        self.published_response: ScreenBacktestResponse | None = None
        """A response whose write failed after the store published it, with `list_published`:
        it's listed, but `response` stays None, so no record references it."""
        self.rank_request: StoredFile | None = None
        """The `rank_update`'s request, once it's written, for an attempt that sends one."""
        self.rank_response: tuple[StoredFile, ScreenBacktestResponse] | None = None
        """The `rank_update`'s response, once it's saved."""

    @property
    def files(self) -> tuple[AttemptFile, ...]:
        """Every file written so far, in order."""
        return tuple(self._files)

    def write(
        self, name: str, data: bytes, role: AttemptRole, *, list_published: bool = False
    ) -> StoredFile:
        """Writes `name`, and lists it. With `list_published`, a write that fails after the store
        published the file, whatever the failure, lists it all the same, so a manifest written
        later lists every file the attempt wrote."""
        try:
            stored = self._store.write(f"{self._directory}/{name}", data)
        except BaseException:
            if list_published:
                self.published(name, data, role)
            raise
        self._files.append(AttemptFile(role, stored))
        return stored

    def write_record(
        self, name: str, record: BaseModel, role: AttemptRole, keep: Callable[[], None]
    ) -> None:
        """Writes a record that comes before a send: a start record, or the update record. `keep`
        records it as written: after a failure while it's written, whatever the failure, a record
        the store published counts as written, so the attempt record agrees with it."""
        data = model_json(record)
        try:
            self.write(name, data, role)
        except BaseException:
            if self.published(name, data, role):
                keep()
            raise
        keep()

    def write_request(self, params: dict[str, object], *, list_published: bool = False) -> None:
        self.request = self.write(
            "request.json", _request_json(params), "provider_request", list_published=list_published
        )

    def save(self, response: ScreenBacktestResponse, *, list_published: bool = False) -> None:
        listed = len(self._files)
        try:
            match response:
                case DecodedResponse(payload=payload):
                    stored = self.write(
                        "response.json",
                        _response_json(payload),
                        "provider_response",
                        list_published=list_published,
                    )
                case UndecodedResponse(body=body):
                    stored = self.write(
                        "response.raw",
                        body,
                        "provider_response_undecoded",
                        list_published=list_published,
                    )
        except BaseException:
            if len(self._files) > listed:
                self.published_response = response
            raise
        self.response = (stored, response)

    def write_rank_update_request(self, params: dict[str, object]) -> None:
        """Writes `rank-update-request.json`, as `request.json` is written, and lists it even when
        the store published it before its write failed."""
        self.rank_request = self.write(
            RANK_UPDATE_REQUEST_FILE,
            _request_json(params),
            "rank_update_request",
            list_published=True,
        )

    def save_rank_update(self, response: ScreenBacktestResponse) -> None:
        """Saves the `rank_update`'s response: `rank-update-response.json`, or `.raw` for a 200
        the wrapper couldn't decode, listed even when the store published it before its write
        failed. Only a completed write is referenced."""
        match response:
            case DecodedResponse(payload=payload):
                name, data, role = (
                    RANK_UPDATE_RESPONSE_FILE,
                    _response_json(payload),
                    "rank_update_response",
                )
            case UndecodedResponse(body=body):
                name, data, role = RANK_UPDATE_RESPONSE_RAW, body, "rank_update_response_undecoded"
        stored = self.write(name, data, role, list_published=True)
        self.rank_response = (stored, response)

    @property
    def rank_update_saved(self) -> bool:
        """Whether the `rank_update`'s response is in the attempt's directory, whole: saved, or
        published by the store before its write failed, as when the directory's sync fails, which
        `files` lists all the same. A resume reads either as saved, since the store publishes a
        file atomically (an attempt stopped after its update record), though `ranking_update`
        references only a completed write."""
        return any(
            file.role in ("rank_update_response", "rank_update_response_undecoded")
            for file in self._files
        )

    def ranking_update(self) -> RankingUpdate:
        """The attempt record's `ranking_update`: the `rank_update`'s request and its saved
        response, when each was written, and the `cost` and `quotaRemaining` of its decoded
        response."""
        response = None
        if self.rank_response is not None:
            stored, saved = self.rank_response
            response = RankUpdateResponse(
                path=stored.path,
                artifact_id=stored.artifact_id,
                form="decoded" if isinstance(saved, DecodedResponse) else "undecoded",
            )
        return RankingUpdate(
            request=None if self.rank_request is None else reference(self.rank_request),
            response=response,
            provider_metadata=response_metadata(
                None if self.rank_response is None else self.rank_response[1]
            ),
        )

    def published(self, name: str, data: bytes, role: AttemptRole) -> bool:
        """Whether an interrupted write of `name` published it whole. If it did, it's listed."""
        stored = published(self._store, f"{self._directory}/{name}", data)
        if stored is not None:
            self._files.append(AttemptFile(role, stored))
        return stored is not None


def reference(stored: StoredFile) -> ArtifactReference:
    """A record's reference to a file the attempt wrote."""
    return ArtifactReference(path=stored.path, artifact_id=stored.artifact_id)


def saved_response(stored: StoredFile, response: ScreenBacktestResponse) -> SavedResponse:
    """The attempt record's reference to its saved response, with its form."""
    return SavedResponse(
        path=stored.path,
        artifact_id=stored.artifact_id,
        form="decoded" if isinstance(response, DecodedResponse) else "undecoded",
    )


def response_metadata(response: ScreenBacktestResponse | None) -> ProviderMetadata:
    """The `provider_metadata` of a saved response: its payload's, when it was decoded, and
    otherwise, or without one, both null."""
    return provider_metadata(response.payload if isinstance(response, DecodedResponse) else None)


def provider_metadata(payload: object) -> ProviderMetadata:
    """`cost` and `quotaRemaining` from the top level of a decoded response's payload, as the
    module says: both null when it isn't an object. The experiment's reader takes them so from a
    saved response, as the attempt that saved it recorded them."""
    if not isinstance(payload, dict):
        return ProviderMetadata(cost=None, quota_remaining=None)
    fields = cast("dict[str, object]", payload)
    return ProviderMetadata(
        cost=_count(fields.get("cost")), quota_remaining=_count(fields.get("quotaRemaining"))
    )


def _count(value: object) -> int | None:
    # A bool is an int in Python, and never a count.
    return value if type(value) is int and value >= 0 else None


def _request_json(params: dict[str, object]) -> bytes:
    return (json.dumps(params, indent=2, allow_nan=False) + "\n").encode("ascii")


def _response_json(payload: object) -> bytes:
    return (json.dumps(payload) + "\n").encode("ascii")
