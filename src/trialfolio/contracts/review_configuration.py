"""The review configuration, `kind: review`, schema version 1.0.0 (docs/contracts.md, review
configuration).

`trialfolio.configuration` reads it from YAML, applying the rules for every configuration file.
This model applies the review's own: the keys, the labels, the declarable settings, and the rules
that span results. Each message from a rule that spans keys names its key, and never a value.
"""

from typing import Annotated, Final, Literal, Self, get_args

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    Strict,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from trialfolio.contracts.common import (
    ContractModel,
    NonEmptyText,
    Purpose,
    ReviewLabel,
    ShortText,
    Title,
    optional_key,
    ordered,
    present,
)
from trialfolio.contracts.screen_settings import DECLARABLE_SETTINGS

ReviewSchemaVersion = Literal["1.0.0"]

REVIEW_SCHEMA_VERSIONS: Final = get_args(ReviewSchemaVersion)
"""The review configuration versions this release reads."""


def _declarable(value: str) -> str:
    if value not in DECLARABLE_SETTINGS:
        raise ValueError(
            "isn't a setting a review can declare. The declarable settings are "
            f"{', '.join(DECLARABLE_SETTINGS[:-1])}, and {DECLARABLE_SETTINGS[-1]}"
        )
    return value


DeclarableSetting = Annotated[
    str,
    AfterValidator(_declarable),
    WithJsonSchema({"type": "string", "enum": list(DECLARABLE_SETTINGS)}),
]
"""One of the 12 screen settings marked declarable (screen settings)."""


class IntendedChange(ContractModel):
    """A change to one setting that a result declares, against the baseline."""

    setting: DeclarableSetting
    reason: ShortText
    """Why the setting was changed, shown in the report: 1 to 500 characters."""


IntendedChanges = Annotated[
    tuple[IntendedChange, ...], Field(min_length=1), Strict(False), BeforeValidator(ordered)
]
"""At least one declared change, in order. A result that declares none leaves the key out."""


class ReviewResult(ContractModel):
    """One compared result: a saved run, by its label."""

    label: ReviewLabel
    run: NonEmptyText
    """The run's directory, as `trialfolio run` wrote it. A relative path is relative to the
    configuration file."""
    description: Annotated[
        ShortText | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """Up to 500 characters, shown in the report."""
    intended_changes: Annotated[
        IntendedChanges | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """The settings this result changes on purpose. Never on the baseline."""

    @field_validator("intended_changes")
    @classmethod
    def _each_setting_once(
        cls, changes: tuple[IntendedChange, ...] | None
    ) -> tuple[IntendedChange, ...] | None:
        first: dict[str, int] = {}
        for index, change in enumerate(changes or ()):
            if change.setting in first:
                raise ValueError(
                    f"declares one setting twice, in [{first[change.setting]}] and [{index}]. "
                    "Declare each setting once"
                )
            first[change.setting] = index
        return changes


class ReviewConfiguration(ContractModel):
    """A review configuration, `kind: review`: saved runs compared against an explicit baseline
    (docs/contracts.md, review configuration)."""

    kind: Literal["review"]
    schema_version: ReviewSchemaVersion
    title: Title
    purpose: Annotated[
        Purpose | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    baseline: ReviewLabel
    """The label of the result the others are compared with."""
    results: Annotated[
        tuple[ReviewResult, ...], Field(min_length=2), Strict(False), BeforeValidator(ordered)
    ]
    """At least two results, in the order the review's outputs list them."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        labels = [result.label for result in self.results]
        for index, label in enumerate(labels):
            first = labels.index(label)
            if first != index:
                raise ValueError(
                    f"`results[{index}].label` repeats the label of `results[{first}]`. Give "
                    "each result its own label"
                )
        if self.baseline not in labels:
            raise ValueError("`baseline` must be the label of one of the `results`")
        index = labels.index(self.baseline)
        if self.results[index].intended_changes is not None:
            raise ValueError(
                f"`results[{index}].intended_changes` is given on the baseline. The other "
                "results' changes are declared against the baseline, so it declares none"
            )
        return self
