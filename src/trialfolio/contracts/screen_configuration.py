"""The screen configuration, `kind: screen`, schema version 1.0.0 (docs/contracts.md, screen
configuration).

`trialfolio.configuration` reads it from YAML. The rules about how a value is written, such as
`010` or `2.5e-1`, apply to the YAML text, so the reader applies them. This model applies the
rest. A decimal reaches it as a `Decimal` or an `int`, and a date as a `date` or as text.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Final, Literal, Self, cast

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)
from pydantic.config import JsonDict

from trialfolio.contracts.common import (
    MAX_SAFE_INTEGER,
    ContractModel,
    IntegerOnly,
    NonEmptyText,
    Purpose,
    Title,
)

SCREEN_SCHEMA_VERSIONS: Final = ("1.0.0",)
"""The screen configuration versions this release reads."""

RANKING_FORMS: Final = ("formula", "name", "id")
"""The key that identifies each ranking form."""

RANKING_FORMS_MESSAGE: Final = (
    "The supported forms are {formula, lower_is_better}, {name}, and {id}."
)

_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _optional_key(schema: JsonDict) -> None:
    # An optional key is left out, never written as null: the schema shows no null and no default.
    schema.pop("default", None)
    branches = schema.pop("anyOf", [])
    if isinstance(branches, list):
        for branch in branches:
            if isinstance(branch, dict) and branch != {"type": "null"}:
                schema.update(branch)


def _present(value: object) -> object:
    if value is None:
        raise ValueError("has no value. Give it one, or leave the key out.")
    return value


def _factset_only(value: object) -> object:
    if _present(value) != "FactSet":
        raise ValueError("must be FactSet, the only supported data vendor (D-16)")
    return value


def _date_from_yaml(value: object) -> object:
    if isinstance(value, datetime):
        raise ValueError("must be a date with no time part, written YYYY-MM-DD")
    if isinstance(value, str):
        if not _DATE_TEXT.fullmatch(value):
            raise ValueError("must be a date written YYYY-MM-DD")
        return date.fromisoformat(value)
    return value


def _decimal_from_yaml(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("must be a number, not true or false")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise ValueError("must be read from the configuration's text, never as a binary float")
    if isinstance(value, str):
        raise ValueError("must be a number written without quotes, such as 0.25")
    return value


def normalize_decimal(value: Decimal) -> Decimal:
    """Removes trailing zeros after the decimal point, then the point if no digits follow it,
    and checks the limits: at most 15 significant digits, at most 4 after the point, and less
    than 10^16. `str()` of the result is the normalized text, in plain notation.
    """
    if not value.is_finite():
        raise ValueError("must be a finite number")
    if value.is_signed():
        raise ValueError("must be 0 or more")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    whole, _, fraction = text.partition(".")
    if len(fraction) > 4:
        raise ValueError("has more than 4 digits after the decimal point")
    # Leading zeros, and a whole number's trailing zeros, aren't significant: 1000 has one
    # significant digit. A fraction has no trailing zeros once normalized.
    if len((whole + fraction).strip("0")) > 15:
        raise ValueError("has more than 15 significant digits")
    if len(whole) > 16:
        raise ValueError("must be less than 10^16")
    return Decimal(text)


ConfigDecimal = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_yaml),
    AfterValidator(normalize_decimal),
    WithJsonSchema(
        {
            "type": "number",
            "minimum": 0,
            "exclusiveMaximum": 10**16,
            "description": "Plain notation, with at most 4 digits after the decimal point and "
            "15 significant digits. Never a string.",
        },
        mode="validation",
    ),
]
"""A configuration decimal, normalized (screen configuration, decimals)."""

ConfigDate = Annotated[date, BeforeValidator(_date_from_yaml)]
"""A YAML date, or text in exactly `YYYY-MM-DD` form, with no time part."""


class FormulaRanking(ContractModel):
    """A ranking by a single formula, the recommended form."""

    formula: NonEmptyText
    lower_is_better: bool


class NameRanking(ContractModel):
    """An existing ranking system in the account, by name. It's recorded as not snapshotted."""

    name: NonEmptyText


class IdRanking(ContractModel):
    """An existing ranking system in the account, by ID. It's recorded as not snapshotted."""

    id: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]


type Ranking = FormulaRanking | NameRanking | IdRanking
"""Exactly one of the ranking forms (screen configuration, ranking forms)."""

_RANKING_MODELS: Final = {"formula": FormulaRanking, "name": NameRanking, "id": IdRanking}


def read_ranking(value: object) -> Ranking:
    """Validates a ranking mapping as the one form its keys name.

    Raises `ValueError` when the mapping names no single supported form, and a
    `ValidationError`, located within the mapping, when that form's fields are invalid.
    """
    if isinstance(value, FormulaRanking | NameRanking | IdRanking):
        return value
    if not isinstance(value, dict):
        raise ValueError(f"must be a mapping. {RANKING_FORMS_MESSAGE}")
    mapping = cast("dict[object, object]", value)
    keys = mapping.keys()
    if "method" in keys:
        raise ValueError(f"can't override the ranking method. {RANKING_FORMS_MESSAGE}")
    if "nodes" in keys or "xml" in keys:
        raise ValueError(
            f"can't be given as nodes or XML, which would change the account's "
            f"APIRankingSystem. {RANKING_FORMS_MESSAGE}"
        )
    forms = [form for form in RANKING_FORMS if form in keys]
    if len(forms) != 1:
        raise ValueError(f"must hold exactly one of formula, name, or id. {RANKING_FORMS_MESSAGE}")
    if "lower_is_better" in keys and forms != ["formula"]:
        raise ValueError(f"allows lower_is_better only with formula. {RANKING_FORMS_MESSAGE}")
    return _RANKING_MODELS[forms[0]].model_validate(mapping)


class ScreenConfiguration(ContractModel):
    """A screen configuration, `kind: screen`: one long-only stock screen backtest, run through
    p123api's screen_backtest (docs/contracts.md, screen configuration).
    """

    kind: Literal["screen"]
    schema_version: Literal["1.0.0"]
    title: Title
    purpose: Annotated[
        Purpose | None,
        BeforeValidator(_present),
        Field(json_schema_extra=_optional_key),
    ] = None
    universe: NonEmptyText
    rules: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, strict=False)]
    ranking: Ranking
    max_holdings: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    benchmark: NonEmptyText
    start_date: ConfigDate
    end_date: ConfigDate
    rebalance_weeks: Annotated[Literal[1, 4], IntegerOnly]
    transaction_price: Literal["open"]
    slippage_percent: ConfigDecimal
    pit_method: Literal["complete"]
    precision: Annotated[Literal[4], IntegerOnly]
    data_vendor: Annotated[
        Literal["FactSet"] | None,
        BeforeValidator(_factset_only),
        Field(json_schema_extra=_optional_key),
    ] = None

    @field_validator("ranking", mode="before")
    @classmethod
    def _one_ranking_form(cls, value: object) -> Ranking:
        return read_ranking(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("`end_date` must be later than `start_date`")
        return self
