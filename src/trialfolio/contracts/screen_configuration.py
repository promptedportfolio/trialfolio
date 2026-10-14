"""The screen configuration, `kind: screen`, schema versions 1.0.0 and 1.1.0 (docs/contracts.md,
screen configuration).

`trialfolio.configuration` reads it from YAML. The rules about how a value is written, such as
`010` or `2.5e-1`, apply to the YAML text, so the reader applies them. This model applies the
rest. A decimal reaches it as a `Decimal` or an `int`, and a date as a `date` or as text.

Version 1.1.0, `ScreenConfigurationV1_1`, adds two ranking forms, a ranking system's definition
and a ranking snapshot, and nothing else (ranking forms). Its settings, `ScreenFieldsV1_1`, are
1.0.0's, from the same bases, with the wider ranking. The definition's file, and the snapshot's
directory, are named here by their paths; reading them is the reader's (ranking definitions).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Final, Literal, Self, cast, get_args

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from trialfolio.contracts.common import (
    MAX_SAFE_INTEGER,
    ContractModel,
    IntegerOnly,
    NonEmptyText,
    OptionalKey,
    Purpose,
    RankingMethod,
    Title,
    optional_key,
    present,
    valid_date_text,
)

ScreenSchemaVersion = Literal["1.0.0"]

SCREEN_SCHEMA_VERSIONS: Final = get_args(ScreenSchemaVersion)
"""The screen configuration versions `trialfolio run` reads, until its path for a ranking
definition is built (release 0.4.0's R04-T12)."""

SCREEN_SCHEMA_VERSIONS_V1_1: Final = ("1.0.0", "1.1.0")
"""The screen configuration versions 0.4.0's readers read: 1.0.0, and 1.1.0, which adds a
ranking given as a definition or a snapshot."""

RANKING_FORMS: Final = ("formula", "name", "id")
"""The key that identifies each ranking form."""

RANKING_FORMS_MESSAGE: Final = (
    "The supported forms are {formula, lower_is_better}, {name}, and {id}."
)

RANKING_FORMS_V1_1: Final = ("formula", "name", "id", "definition", "snapshot")
"""The key that identifies each ranking form of screen configuration 1.1.0."""

RANKING_FORMS_MESSAGE_V1_1: Final = (
    "The supported forms are {formula, lower_is_better}, {name}, {id}, "
    "{definition, ranking_method}, and {snapshot}."
)


def _factset_only(value: object) -> object:
    if present(value) != "FactSet":
        raise ValueError("must be FactSet, the only supported data vendor (D-16)")
    return value


def _date_from_yaml(value: object) -> object:
    if isinstance(value, datetime):
        raise ValueError("must be a date with no time part, written YYYY-MM-DD")
    if isinstance(value, str):
        return date.fromisoformat(valid_date_text(value))
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


def _positive(value: Decimal) -> Decimal:
    if value.is_zero():
        raise ValueError(
            "must be greater than 0: Portfolio123 reads a weight of 0 as equal weighting"
        )
    return value


ConfigWeight = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_yaml),
    AfterValidator(normalize_decimal),
    AfterValidator(_positive),
    WithJsonSchema(
        {
            "type": "number",
            "exclusiveMinimum": 0,
            "exclusiveMaximum": 10**16,
            "description": "A node's weight: greater than 0, in plain notation, with at most 4 "
            "digits after the decimal point and 15 significant digits. Never a string.",
        },
        mode="validation",
    ),
]
"""A ranking variant's weight: a configuration decimal, normalized, and greater than 0 (ranking
variants)."""

ConfigDate = Annotated[date, BeforeValidator(_date_from_yaml)]
"""A YAML date, or text in exactly `YYYY-MM-DD` form, with no time part."""

MaxHoldings = Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
"""`max_holdings`: 1 or more."""

RebalanceWeeks = Annotated[Literal[1, 4], IntegerOnly]
"""`rebalance_weeks`: 1 or 4, the values a release has verified."""


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


class DefinitionRanking(ContractModel):
    """A ranking system's definition, from 1.1.0: the XML in a file beside the configuration. Each
    case writes it into `ApiRankingSystem` with `rank_update`, and its backtest ranks by that
    system's name."""

    definition: NonEmptyText
    """The path of the file that holds the definition, relative to the configuration file."""
    ranking_method: RankingMethod
    """Required, so the method is always explicit: `percentile_nas_negative`, sent as 2, or
    `percentile_nas_neutral`, sent as 4."""


class SnapshotRanking(ContractModel):
    """A ranking snapshot, from 1.1.0: a ranking system saved in the account, as an earlier
    `trialfolio run` of a snapshot configuration read it. The definition and the ranking method
    are the snapshot's."""

    snapshot: NonEmptyText
    """The path of the snapshot's directory, relative to the configuration file."""


type Ranking = FormulaRanking | NameRanking | IdRanking
"""Exactly one of the ranking forms (screen configuration, ranking forms)."""

type RankingV1_1 = FormulaRanking | NameRanking | IdRanking | DefinitionRanking | SnapshotRanking
"""Exactly one of screen configuration 1.1.0's ranking forms."""

_RANKING_MODELS: Final = {"formula": FormulaRanking, "name": NameRanking, "id": IdRanking}

_RANKING_MODELS_V1_1: Final = {
    **_RANKING_MODELS,
    "definition": DefinitionRanking,
    "snapshot": SnapshotRanking,
}


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
            f"ApiRankingSystem. {RANKING_FORMS_MESSAGE}"
        )
    later = [form for form in RANKING_FORMS_V1_1 if form in keys and form not in RANKING_FORMS]
    if later:
        raise ValueError(
            f"gives {later[0]}, a form that needs schema_version 1.1.0. {RANKING_FORMS_MESSAGE}"
        )
    forms = [form for form in RANKING_FORMS if form in keys]
    if len(forms) != 1:
        raise ValueError(f"must hold exactly one of formula, name, or id. {RANKING_FORMS_MESSAGE}")
    if "lower_is_better" in keys and forms != ["formula"]:
        raise ValueError(f"allows lower_is_better only with formula. {RANKING_FORMS_MESSAGE}")
    return _RANKING_MODELS[forms[0]].model_validate(mapping)


def read_ranking_v1_1(value: object) -> RankingV1_1:
    """Validates a ranking mapping of screen configuration 1.1.0 as the one form its keys name:
    one of 1.0.0's, a definition, or a snapshot. `lower_is_better` goes only with `formula`, and
    `ranking_method` only with `definition`, which requires it (ranking forms).

    Raises `ValueError` when the mapping names no single supported form, and a
    `ValidationError`, located within the mapping, when that form's fields are invalid.
    """
    if isinstance(
        value, FormulaRanking | NameRanking | IdRanking | DefinitionRanking | SnapshotRanking
    ):
        return value
    if not isinstance(value, dict):
        raise ValueError(f"must be a mapping. {RANKING_FORMS_MESSAGE_V1_1}")
    mapping = cast("dict[object, object]", value)
    keys = mapping.keys()
    if "method" in keys:
        raise ValueError(f"can't override the ranking method. {RANKING_FORMS_MESSAGE_V1_1}")
    if "nodes" in keys or "xml" in keys:
        raise ValueError(
            "can't be given as nodes or XML in the configuration itself. A ranking system's "
            f"definition is given in a file, named by definition. {RANKING_FORMS_MESSAGE_V1_1}"
        )
    forms = [form for form in RANKING_FORMS_V1_1 if form in keys]
    if len(forms) != 1:
        raise ValueError(
            "must hold exactly one of formula, name, id, definition, or snapshot. "
            f"{RANKING_FORMS_MESSAGE_V1_1}"
        )
    if "lower_is_better" in keys and forms != ["formula"]:
        raise ValueError(f"allows lower_is_better only with formula. {RANKING_FORMS_MESSAGE_V1_1}")
    if "ranking_method" in keys and forms != ["definition"]:
        reason = ": a snapshot records its system's ranking method" if forms == ["snapshot"] else ""
        raise ValueError(
            f"allows ranking_method only with definition{reason}. {RANKING_FORMS_MESSAGE_V1_1}"
        )
    return _RANKING_MODELS_V1_1[forms[0]].model_validate(mapping)


# A screen's settings come from three bases, so that 1.0.0's and 1.1.0's share every setting but
# the ranking. Pydantic orders the fields of the bases last to first, so `ranking` stays third.


class _ScreenBeforeRanking(ContractModel):
    """The settings before the ranking: the universe and the rules."""

    universe: NonEmptyText
    rules: Annotated[tuple[NonEmptyText, ...], Field(min_length=1, strict=False)]

    @field_validator("rules", mode="before")
    @classmethod
    def _ordered_rules(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            raise ValueError("must be an ordered list of formulas")
        return cast("list[object] | tuple[object, ...]", value)


class _ScreenRanking(ContractModel):
    """Screen configuration 1.0.0's ranking: a formula, a name, or an ID."""

    ranking: Ranking

    @field_validator("ranking", mode="before")
    @classmethod
    def _one_ranking_form(cls, value: object) -> Ranking:
        return read_ranking(value)


class _ScreenRankingV1_1(ContractModel):
    """Screen configuration 1.1.0's ranking: 1.0.0's forms, a definition, or a snapshot."""

    ranking: RankingV1_1

    @field_validator("ranking", mode="before")
    @classmethod
    def _one_ranking_form(cls, value: object) -> RankingV1_1:
        return read_ranking_v1_1(value)


class _ScreenAfterRanking(ContractModel):
    """The settings after the ranking, from `max_holdings` to `data_vendor`."""

    max_holdings: MaxHoldings
    benchmark: NonEmptyText
    start_date: ConfigDate
    end_date: ConfigDate
    rebalance_weeks: RebalanceWeeks
    transaction_price: Literal["open"]
    slippage_percent: ConfigDecimal
    pit_method: Literal["complete"]
    precision: Annotated[Literal[4], IntegerOnly]
    data_vendor: Annotated[
        Literal["FactSet"] | None,
        BeforeValidator(_factset_only),
        Field(json_schema_extra=optional_key),
    ] = None

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("`end_date` must be later than `start_date`")
        return self


class ScreenFields(_ScreenAfterRanking, _ScreenRanking, _ScreenBeforeRanking):
    """A screen's settings: a screen configuration's keys from `universe` to `data_vendor`, with
    their types, rules, and verified values. An experiment's baseline is one (docs/contracts.md,
    the baseline)."""


class ScreenFieldsV1_1(_ScreenAfterRanking, _ScreenRankingV1_1, _ScreenBeforeRanking):
    """A screen's settings in screen configuration 1.1.0, and in an experiment configuration
    1.1.0's baseline: 1.0.0's, with a ranking that may also be a ranking system's definition, in
    a file, or a ranking snapshot (docs/contracts.md, ranking forms)."""


class _ScreenHeader(ContractModel):
    """The keys a screen configuration has before its settings."""

    kind: Literal["screen"]
    schema_version: ScreenSchemaVersion
    title: Title
    purpose: OptionalKey[Purpose] = None


# Pydantic orders the fields of the bases last to first, so the header's come first, as in the
# file and the committed schema.
class ScreenConfiguration(ScreenFields, _ScreenHeader):
    """A screen configuration, `kind: screen`: one long-only stock screen backtest, run through
    p123api's screen_backtest (docs/contracts.md, screen configuration).
    """


class _ScreenHeaderV1_1(ContractModel):
    """The keys a screen configuration 1.1.0 has before its settings."""

    kind: Literal["screen"]
    schema_version: Literal["1.1.0"]
    title: Title
    purpose: OptionalKey[Purpose] = None


class ScreenConfigurationV1_1(ScreenFieldsV1_1, _ScreenHeaderV1_1):
    """A screen configuration 1.1.0, `kind: screen`: one long-only stock screen backtest, whose
    ranking may also be a ranking system's definition or a ranking snapshot, which each case
    writes into `ApiRankingSystem` before its backtest (docs/contracts.md, screen configuration).
    """
