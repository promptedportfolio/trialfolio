"""What every reader of saved records checks of a file, whatever kind of output it reads: a run's
and an experiment's readers, through `trialfolio.record_checks`, the reader of a ranking snapshot,
`trialfolio.snapshots`, and the reader of the normalized tables, `trialfolio.tables`
(docs/contracts.md, a complete run, checking the records, and reading a snapshot).

- **A manifest,** read before anything else: a directory without one didn't finish.
- **A listed file** exists, with the size and `artifact_id` its manifest's entry records.
- **A record** is a JSON object, with a schema version its reader reads, valid against its model;
  a message names only the model's own fields, which `invalid_fields` gives, as the tables' reader
  names a row's.

Each check is given the function that makes its reader's error, and how its messages name the
file, such as "`plan.json`" or "its `snapshot.json`", so each reader refuses in its own words.
Nothing here imports the configuration's reader, which imports the snapshot's: so the snapshot's
reader shares these checks, where it can't import `trialfolio.record_checks`.

Nothing here writes or logs.
"""

import json
from collections.abc import Callable, Collection
from typing import Protocol, cast

from pydantic import BaseModel, ValidationError

from trialfolio.canonical import sha256_hex
from trialfolio.display import visible
from trialfolio.errors import reason_of
from trialfolio.storage import StoreReader

type Refused = Callable[[str], Exception]
"""Makes a reader's error for a problem: a sentence that names no value, such as "`plan.json`
isn't JSON."."""


class _Listed(Protocol):
    """A manifest's entry for a file, of any kind of output."""

    @property
    def path(self) -> str: ...
    @property
    def size(self) -> int: ...
    @property
    def artifact_id(self) -> str: ...


def named(path: str) -> str:
    """A path as a message names it: in backticks, with each character that isn't visible
    escaped."""
    return f"`{visible(path)}`"


def artifact_id(content: bytes) -> str:
    """The `artifact_id` of a file that holds `content`: `sha256:` and the hex SHA-256 of its
    bytes."""
    return "sha256:" + sha256_hex(content)


def matches(content: bytes, artifact: _Listed) -> bool:
    """Whether `content` has the size and `artifact_id` the manifest's entry records."""
    return len(content) == artifact.size and artifact_id(content) == artifact.artifact_id


def read_manifest(store: StoreReader, path: str, kind: str, refused: Refused) -> bytes:
    """The bytes of the manifest at `path` of the output in `store`, rooted at its directory,
    whose `kind`, such as "run", the messages give."""
    try:
        return store.read(path)
    except FileNotFoundError:
        raise refused(
            f"it has no {path}. Trial Folio writes a {kind}'s manifest last, so a {kind} without"
            " one didn't finish."
        ) from None
    except NotADirectoryError:
        raise refused("it isn't a directory.") from None
    except OSError as error:
        raise refused(f"its {path} can't be read ({reason_of(error)}).") from None


def read_listed(store: StoreReader, artifact: _Listed, written: str, refused: Refused) -> bytes:
    """The bytes of a file the manifest lists, checked against its size and `artifact_id`.
    `written` says when the output wrote it, after "it changed after ", such as "the run wrote
    it"."""
    try:
        content = store.read(artifact.path)
    except FileNotFoundError:
        raise refused(f"its manifest lists {named(artifact.path)}, which is missing.") from None
    except OSError as error:
        raise refused(
            f"{named(artifact.path)}, which its manifest lists, can't be read ({reason_of(error)})."
        ) from None
    if not matches(content, artifact):
        raise refused(
            f"{named(artifact.path)} doesn't match its artifact_id in the manifest, so it changed"
            f" after {written}."
        )
    return content


def json_object(content: bytes, file: str, refused: Refused) -> dict[str, object]:
    """The JSON object in `content`, the file that `file` names."""
    try:
        loaded: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise refused(f"{file} isn't JSON.") from None
    if not isinstance(loaded, dict):
        raise refused(f"{file} isn't a JSON object.")
    return cast("dict[str, object]", loaded)


def check_version(
    version: object,
    readable: Collection[str],
    file: str,
    refused: Refused,
    unknown: Callable[[], Exception],
) -> None:
    """Checks that `version`, the schema version the file that `file` names holds, is one of
    `readable`. `unknown` makes the reader's `artifact.unknown_schema_version`, whose message
    never gives the version, which is text from the file."""
    if version in readable:
        return
    if not isinstance(version, str):
        raise refused(f"{file} has no schema version.")
    raise unknown()


def validated[M: BaseModel](
    model: type[M], content: bytes, file: str, what: str, refused: Refused
) -> M:
    """`content`, the file that `file` names, as `model`. `what` names the model in a message,
    such as "run manifest"."""
    try:
        return model.model_validate_json(content)
    except ValidationError as error:
        fields = invalid_fields(error, model)
        check = f"check `{'`, `'.join(fields)}`" if fields else "check its fields"
        raise refused(f"{file} isn't a valid {what}: {check}.") from None


def invalid_fields(error: ValidationError, model: type[BaseModel]) -> list[str]:
    """The fields of `model` that `error` finds invalid, sorted. Only the model's own fields are
    named: an unexpected key is text from the file."""
    details = error.errors(include_url=False, include_input=False, include_context=False)
    return sorted(
        {
            str(detail["loc"][0])
            for detail in details
            if detail["loc"] and detail["loc"][0] in model.model_fields
        }
    )
