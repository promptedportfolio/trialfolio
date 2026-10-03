"""Canonical JSON follows RFC 8785 (docs/contracts.md, canonical hashing).

Traces to R01-AC25: the expected bytes are written by hand from RFC 8785. A whole-number float is
written as ECMAScript writes it, `1.0` as `1`, and text keeps its UTF-8, `Café` never
`Caf\\u00e9`. The samples from the RFC itself check the parts of the scheme a plan relies on:
property order, string escapes, and numbers. Also traces to the decimals rules in
docs/contracts.md, screen configuration: a decimal within the limits is written in plain
notation, both in the request body and in the canonical form.
"""

import json
import struct

import pytest

from trialfolio.canonical import canonical_json


def test_a_whole_number_float_is_written_as_ecmascript_writes_it() -> None:
    assert canonical_json({"slippage": 1.0}) == b'{"slippage":1}'
    assert canonical_json({"slippage": 0.25}) == b'{"slippage":0.25}'


def test_non_ascii_text_is_written_as_its_utf8_never_escaped() -> None:
    assert canonical_json({"title": "Café"}) == b'{"title":"Caf\xc3\xa9"}'


def test_the_rfc_sample_canonicalizes_as_the_rfc_gives_it() -> None:
    # RFC 8785, section 3.2.2's input, and section 3.2.3's canonical form of it.
    parsed = json.loads(
        r"""{
          "numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],
          "string": "\u20ac$\u000F\u000aA'\u0042\u0022\u005c\\\"\/",
          "literals": [null, true, false]
        }"""
    )

    assert canonical_json(parsed) == (
        b'{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        b'"string":"\xe2\x82\xac$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )


def test_properties_are_sorted_by_their_utf16_code_units() -> None:
    # RFC 8785, section 3.2.3's test data. The emoji, a surrogate pair in UTF-16, sorts before
    # U+FB33, though its code point is larger.
    parsed = json.loads(
        r"""{
          "\u20ac": "Euro Sign",
          "\r": "Carriage Return",
          "\ufb33": "Hebrew Letter Dalet With Dagesh",
          "1": "One",
          "\ud83d\ude00": "Emoji: Grinning Face",
          "\u0080": "Control",
          "\u00f6": "Latin Small Letter O With Diaeresis"
        }"""
    )

    order = list(json.loads(canonical_json(parsed)).values())

    assert order == [
        "Carriage Return",
        "One",
        "Control",
        "Latin Small Letter O With Diaeresis",
        "Euro Sign",
        "Emoji: Grinning Face",
        "Hebrew Letter Dalet With Dagesh",
    ]


@pytest.mark.parametrize(
    ("ieee_754", "expected"),
    [
        # From RFC 8785, appendix B.
        ("0000000000000000", b"0"),
        ("8000000000000000", b"0"),
        ("0000000000000001", b"5e-324"),
        ("4340000000000000", b"9007199254740992"),
        ("444b1ae4d6e2ef4f", b"999999999999999900000"),
        ("444b1ae4d6e2ef50", b"1e+21"),
        ("3eb0c6f7a0b5ed8c", b"9.999999999999997e-7"),
        ("3eb0c6f7a0b5ed8d", b"0.000001"),
        ("41b3de4355555555", b"333333333.3333333"),
        ("43143ff3c1cb0959", b"1424953923781206.2"),
    ],
)
def test_numbers_are_written_as_the_rfc_samples_give_them(ieee_754: str, expected: bytes) -> None:
    (number,) = struct.unpack(">d", bytes.fromhex(ieee_754))

    assert canonical_json(number) == expected


@pytest.mark.parametrize(
    "normalized",
    [
        "0",
        "0.0001",
        "0.1",
        "0.25",
        "1",
        "1.5",
        "100",
        "12345678901.2345",
        "99999999999.9999",
        "123456789012345",
        "1000000000000000",
        "9999999999999990",
    ],
)
def test_a_decimal_within_the_limits_stays_in_plain_notation(normalized: str) -> None:
    # At most 15 significant digits, 4 after the point, and less than 10^16: its float's
    # shortest form has exactly its digits.
    sent = float(normalized)
    whole = "." not in normalized

    assert json.dumps(sent) == (f"{normalized}.0" if whole else normalized)
    assert canonical_json(sent) == normalized.encode()


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        (2**53, "an integer beyond 2^53 - 1"),
        (float("nan"), "an infinite or NaN number"),
        ({1: "key"}, "a key that isn't text"),
        ("\ud800", "text that isn't valid Unicode"),
    ],
)
def test_a_value_json_cant_hold_exactly_is_refused_without_quoting_it(
    value: object, problem: str
) -> None:
    with pytest.raises(ValueError, match="can't be written as canonical JSON") as raised:
        canonical_json(value)

    assert problem in str(raised.value)
    assert "9007199254740992" not in str(raised.value)
