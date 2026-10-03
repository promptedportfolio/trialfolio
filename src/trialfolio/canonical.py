"""Canonical JSON and the hashes computed from it (docs/contracts.md, canonical hashing).

These are `canonicalization_version` 1's rules. Canonical JSON follows RFC 8785, the JSON
Canonicalization Scheme, through Trail of Bits' `rfc8785` package, applied to a model's
serialized form. Never `json.dumps`, which differs from RFC 8785 in two ways that matter here: it
writes the float `1.0` as `1.0`, where RFC 8785 writes `1`, and it escapes non-ASCII text, where
RFC 8785 keeps the UTF-8.
"""

import hashlib
from typing import Final

import rfc8785

CANONICALIZATION_VERSION: Final = 1
"""The version of the rules this module applies."""


def canonical_json(value: object) -> bytes:
    """Returns the RFC 8785 canonical form of `value`: JSON data as `model_dump(mode="json")`
    returns it, built from dicts with text keys, lists or tuples, text, integers, floats,
    booleans, and `None`.

    Raises `ValueError` for anything RFC 8785 can't write exactly: an integer beyond 2^53 - 1, an
    infinite or NaN float, text that isn't valid Unicode, a key that isn't text, or another type.
    """
    try:
        # The package checks every value as it writes it; its type for them is private.
        return rfc8785.dumps(value)  # pyright: ignore[reportArgumentType]
    except rfc8785.IntegerDomainError:
        problem = "an integer beyond 2^53 - 1"
    except rfc8785.FloatDomainError:
        problem = "an infinite or NaN number"
    except rfc8785.CanonicalizationError:
        problem = "text that isn't valid Unicode, a key that isn't text, or another type"
    # The package's own messages quote the value, which can be a configuration value.
    raise ValueError(f"can't be written as canonical JSON: it holds {problem}")


def sha256_hex(content: bytes) -> str:
    """The SHA-256 of `content`, as 64 lowercase hex digits."""
    return hashlib.sha256(content).hexdigest()
