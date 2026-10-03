"""Types and rules the contract models share (docs/contracts.md)."""

import re
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Final, Literal

from pydantic import (
    UUID4,
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from trialfolio.errors import ErrorCode

MAX_SAFE_INTEGER: Final = 2**53 - 1
"""The largest integer a JSON number keeps exactly, 9007199254740991 (screen configuration)."""


class ContractModel(BaseModel):
    """The base of every contract model: strict, closed to unknown fields, and frozen.

    Strict mode coerces nothing, and validation errors never carry the input (Pydantic
    conventions, logging).
    """

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        use_attribute_docstrings=True,
    )


def _integer_only(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("must be an integer")
    return value


IntegerOnly: Final = BeforeValidator(_integer_only)
"""Annotates a `Literal` of integers. A literal compares by equality, so without it, `true`
would pass as 1 and `4.0` as 4."""

# Patterns use [0-9], never \d, which matches other scripts' digits too.

SemanticVersion = Annotated[
    str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
]
"""`<major>.<minor>.<patch>`, with no prefix and no leading zeros (versioning)."""

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
"""`sha256:` and 64 lowercase hex digits: an `artifact_id` or a `plan_hash` (identity)."""

CaseId = Annotated[str, StringConstraints(pattern=r"^case-[0-9a-f]{16}$")]
"""`case-` and the first 16 hex digits of a SHA-256 (plan hashing)."""

_UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def _canonical_uuid(value: object) -> object:
    # Pydantic reads a UUID from JSON in other forms too, such as without hyphens.
    if isinstance(value, str) and not _UUID_TEXT.fullmatch(value):
        raise ValueError("must be a version 4 UUID in canonical form: lowercase, with hyphens")
    return value


AttemptId = Annotated[UUID4, BeforeValidator(_canonical_uuid)]
"""A random version 4 UUID, written in canonical form (identity)."""

ResultLabel = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
"""A result label (identity)."""

SettingName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
"""A normalized setting name, in snake_case (settings.csv)."""

PackageVersion = Annotated[str, StringConstraints(pattern=r"^[0-9][0-9A-Za-z.+!_-]*$")]
"""An installed package's version, as `importlib.metadata.version` reports it."""

LicenseId = Annotated[str, StringConstraints(pattern=r"^LicenseRef-[A-Za-z0-9.-]+$")]
"""An SPDX license reference, such as `LicenseRef-NSPRL-1.0`."""

NOT_BLANK: Final = r"[^\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]"
"""The pattern of text that isn't blank: a character that isn't whitespace, meaning Unicode's
White_Space characters. They're listed rather than written `\\S`, which Pydantic's Rust regex,
Python's `re`, and a JSON Schema validator's ECMAScript regex each read differently."""

DATE_PATTERN: Final = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
"""`YYYY-MM-DD` in form. `valid_date_text` checks it's a calendar date."""

INTEGER_PATTERN: Final = r"0|[1-9][0-9]*"
"""An integer in plain decimal digits, with no sign or leading zero."""

Count = Annotated[int, Field(ge=0)]

NonEmptyText = Annotated[str, StringConstraints(min_length=1, pattern=NOT_BLANK)]
"""Non-empty text: at least one character that isn't whitespace."""

Title = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=NOT_BLANK)]
"""A configuration's title: 1 to 200 characters, not all whitespace."""

Purpose = Annotated[str, StringConstraints(min_length=1, max_length=2000, pattern=NOT_BLANK)]
"""A configuration's declared purpose: 1 to 2,000 characters, not all whitespace."""


def valid_date_text(value: str) -> str:
    """Raises `ValueError` unless `value` is a calendar date written `YYYY-MM-DD`. The message
    never quotes the value."""
    if not re.fullmatch(DATE_PATTERN, value):
        raise ValueError("must be a date written YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("isn't a calendar date") from None
    return value


DateText = Annotated[
    str,
    StringConstraints(pattern=f"^{DATE_PATTERN}$"),
    AfterValidator(valid_date_text),
]
"""A calendar date as `YYYY-MM-DD` text."""


def _in_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("must be a UTC time")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_in_utc)]
"""A UTC time. It's written in ISO 8601 with a `Z` suffix (canonical hashing)."""


RELATIVE_PATH_PATTERN: Final = r"[^/\\:]+(/[^/\\:]+)*"
"""Segments separated by `/`, none empty, and no `\\` or `:`, so the path is relative on Windows
too. `valid_relative_path` also rejects `.` and `..` segments, and NUL."""


def valid_relative_path(value: str) -> str:
    """Raises `ValueError` unless `value` is a path relative to the output root: segments
    separated by `/`, none of them empty, `.`, or `..`, and no NUL, which no file name holds. The
    `ArtifactStore` and the models check paths with this one rule."""
    if not re.fullmatch(RELATIVE_PATH_PATTERN, value) or "\0" in value:
        raise ValueError("must be a relative path with / separators, and no \\, :, or NUL")
    if any(part in (".", "..") for part in value.split("/")):
        raise ValueError("must stay inside the output directory, with no . or .. segments")
    return value


RelativePath = Annotated[
    str,
    StringConstraints(pattern=f"^{RELATIVE_PATH_PATTERN}$"),
    AfterValidator(valid_relative_path),
]
"""A path relative to the output root, with `/` separators. Never absolute (artifact storage)."""

Provenance = Literal["verified", "user_supplied", "inferred", "unknown"]

FlagCode = Literal[
    "critical_unexplained_mismatch",
    "critical_unknown",
    "intended_change_not_observed",
    "inferred_default",
    "time_dependent_default",
    "unsupported_value",
    "not_snapshotted",
    "coverage_mismatch",
    "identical_source",
]

UnavailableReason = Literal[
    "absent_from_layout",
    "blank_in_source",
    "unparseable_in_source",
    "not_applicable",
    "not_supported",
    "input_unavailable",
]

MetricUnit = Annotated[
    str, StringConstraints(pattern=r"^(percent|ratio|count|days|date|currency:[A-Z]{3})$")
]
"""A metric's unit (metrics and missing values)."""

SettingUnit = Literal["count", "weeks", "percent"]
"""The units the screen settings use."""

SettingCategory = Literal[
    "dates",
    "benchmark",
    "currency",
    "costs",
    "execution",
    "universe",
    "data_source",
    "strategy",
    "other",
]

CRITICAL_CATEGORIES: Final[frozenset[SettingCategory]] = frozenset(
    {
        "dates",
        "benchmark",
        "currency",
        "costs",
        "execution",
        "universe",
        "data_source",
        "strategy",
    }
)
"""Every category except `other` is critical (settings and differences)."""

Interpretation = Literal["interpreted", "not_interpreted"]

CommandOutcome = Literal["completed", "partial", "failed"]

NotAssessed = Literal["not_assessed"]

AUTHENTICATION_REQUEST: Final = "POST /auth"
"""The exchange of Trial Folio's own authentication call (HTTP exchanges)."""


def require_unique[T](values: tuple[T, ...], what: str) -> None:
    """Raises `ValueError` when `values` repeats an element."""
    if len(set(values)) != len(values):
        raise ValueError(f"{what} must not repeat")


class ErrorDetail(ContractModel):
    """An error, as a stable code and an actionable message (errors)."""

    code: ErrorCode
    message: NonEmptyText


def check_outcome(outcome: CommandOutcome, error: ErrorDetail | None) -> None:
    """Raises `ValueError` unless `error` is null exactly when the outcome is `completed`, and
    the outcome is `partial` exactly for `execution.partial` (JSON summary)."""
    if (error is None) != (outcome == "completed"):
        raise ValueError("error must be given exactly when the outcome isn't completed")
    if error is not None and (outcome == "partial") != (error.code == "execution.partial"):
        raise ValueError("the outcome is partial exactly for execution.partial")


class WrapperVersions(ContractModel):
    """The installed `p123api`, which sends the requests (plan contents)."""

    p123api: PackageVersion


class TransportVersions(ContractModel):
    """The installed `requests` and `urllib3`, which carry the wrapper's requests."""

    requests: PackageVersion
    urllib3: PackageVersion
