"""The license acknowledgment, the CLI's side (docs/contracts.md, license acknowledgment; D-17,
LIC-12).

The core never checks it (REQ-03): each interface presents it, as the CLI does. An acknowledgment
covers one license identifier and one notice version, `LicenseRef-NSPRL-1.1` and `1.0`, and only a
change to either asks again. There are three ways to give one:

- **Interactively,** by typing `accept` when stdin and stderr are both terminals. The CLI records
  it, with the method `interactive`.
- **`trialfolio license --accept`,** which records it, with the method `command`.
- **`TRIALFOLIO_ACCEPT_LICENSE`,** set to exactly `<license_id>/<notice_version>`, which
  acknowledges for that process only and records nothing. Any other value is rejected; an empty
  one counts as unset.

The record, `acknowledgment.json` in the per-user configuration directory, holds only the four
fields of `AcknowledgmentRecord`. It's never transmitted.
"""

import os
import secrets
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import ValidationError

from trialfolio.contracts.acknowledgment import AcknowledgmentRecord
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.userdirs import config_directory

ACCEPT_VARIABLE: Final = "TRIALFOLIO_ACCEPT_LICENSE"
ACCEPT_VALUE: Final = f"{LICENSE_ID}/{NOTICE_VERSION}"
"""The exact value of `TRIALFOLIO_ACCEPT_LICENSE` that acknowledges the current license and
notice version."""

ACCEPT_ANSWER: Final = "accept"
"""What the user types to acknowledge interactively. Any other answer is a refusal."""

RECORD_NAME: Final = "acknowledgment.json"


def record_path(environ: Mapping[str, str]) -> Path:
    """Where the acknowledgment record is: `acknowledgment.json` in the per-user configuration
    directory."""
    return config_directory(environ) / RECORD_NAME


def environment_acknowledgment(environ: Mapping[str, str]) -> bool | None:
    """Whether `TRIALFOLIO_ACCEPT_LICENSE` acknowledges the current license and notice version:
    None when it's unset or empty, True when it's exactly `ACCEPT_VALUE`, and False for any other
    value, which is rejected."""
    value = environ.get(ACCEPT_VARIABLE)
    if not value:
        return None
    return value == ACCEPT_VALUE


def read_record(path: Path) -> AcknowledgmentRecord | None:
    """The record at `path`, or None when there's none, or it can't be read or isn't a valid
    record, which asks again as a missing one does."""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    try:
        return AcknowledgmentRecord.model_validate_json(content)
    except ValidationError:
        return None


def is_current(record: AcknowledgmentRecord | None) -> bool:
    """Whether `record` acknowledges the current license identifier and notice version."""
    return (
        record is not None
        and record.license_id == LICENSE_ID
        and record.notice_version == NOTICE_VERSION
    )


def write_record(
    path: Path, method: Literal["interactive", "command"], acknowledged_at: datetime
) -> AcknowledgmentRecord:
    """Records an acknowledgment of the current license and notice version at `path`, replacing
    any earlier record, and returns it. The file is written whole or not at all.

    Raises `OSError` when it can't be written, and `ValueError` unless `acknowledged_at` is UTC.
    """
    record = AcknowledgmentRecord(
        license_id=LICENSE_ID,
        notice_version=NOTICE_VERSION,
        acknowledged_at=acknowledged_at,
        method=method,
    )
    data = (record.model_dump_json(indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    # A record isn't an artifact: a new license replaces it, so os.replace is what's wanted.
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with open(temporary, "xb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return record
