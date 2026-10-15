"""What the readers of saved records share in checking them: `runs.py`, which reads a run back for
`trialfolio report` and a review, and `experiment_records.py`, which reads an experiment's records
for a resume (docs/contracts.md, a complete run, and checking the records).

- **A record.** It's a JSON object, with a schema version its reader reads, and valid against its
  model, and a manifest's entry for it gives a version its reader reads, or none.
- **A plan.** It recomputes to its `plan_hash` (plan hashing).
- **A listed file.** It has the size and `artifact_id` its manifest's entry records.
- **A case's normalized tables.** Each reads back as a valid table, its rows are labeled with the
  case's `case_id`, `metrics.csv` holds one row for each of the layout's metrics, in order, each in
  the metric's unit, `settings.csv` one for each of the plan's settings, in order, and each row was
  drawn from the file it should be.

The two readers refuse differently: a run's error names the run as its reader is told to, once
the check has failed, and an experiment's names the output directory. So `RecordChecks` takes the
functions that make a reader's errors, and the schema versions it reads. Each reader words the
problems with a listed file and with the tables in its own sentences, and checks the tables in its
own order, so for those this module gives only the tests.

Nothing here reads a file, writes, or logs.
"""

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from trialfolio.canonical import sha256_hex
from trialfolio.contracts.experiment_manifest import ExperimentArtifact
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.manifest import ManifestArtifact
from trialfolio.contracts.plan import Plan, PlanSetting
from trialfolio.contracts.tables import MetricsRow, SettingsRow
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import METRICS
from trialfolio.planning import plan_hash

_METRIC_ROWS: Final = tuple((metric.subject, metric.metric_id, metric.unit) for metric in METRICS)
"""`metrics.csv`'s rows, in order, by subject and `metric_id`, with the unit the layout fixes."""


@dataclass(frozen=True)
class RecordChecks:
    """A reader's checks of its records, which refuse as the reader does."""

    refused: Callable[[str], Exception]
    """Makes the reader's `input.not_a_run` for a problem: a sentence that names no value, such as
    "`plan.json` isn't JSON."."""
    unknown_version: Callable[[str, str], Exception]
    """Makes the reader's `artifact.unknown_schema_version` for the file at a path, from a sentence
    that names the versions this version reads, never the file's own, which is text from a file."""
    readable: Mapping[str, tuple[str, tuple[str, ...]]]
    """The schema versions the reader reads, for each kind of file whose version it checks, with
    what they're called in messages, such as "plans"."""
    manifest: str
    """How a message names the manifest whose entry gives a file's version, such as "its
    manifest"."""

    def record[M: BaseModel](self, model: type[M], content: bytes, path: str, kind: str) -> M:
        """The record of `kind` in `content`, the file at `path`, checked against its schema
        version, then its model."""
        self.check_version(self.json_object(content, path).get("schema_version"), path, kind)
        return self.validated(model, content, path, self.readable[kind][0].removesuffix("s"))

    def json_object(self, content: bytes, path: str) -> dict[str, object]:
        """The JSON object in `content`, the file at `path`."""
        try:
            loaded: object = json.loads(content)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise self.refused(f"{named(path)} isn't JSON.") from None
        if not isinstance(loaded, dict):
            raise self.refused(f"{named(path)} isn't a JSON object.")
        return cast("dict[str, object]", loaded)

    def check_version(self, version: object, path: str, kind: str, *, listed: bool = False) -> None:
        """Checks the schema version of the file at `path`, from the file itself or, when
        `listed`, from its manifest's entry, where a file without one has none. A kind of file
        whose version the reader doesn't check, such as a saved response, passes."""
        if kind not in self.readable:
            return
        name, readable = self.readable[kind]
        if (listed and version is None) or version in readable:
            return
        if not isinstance(version, str):
            raise self.refused(f"{named(path)} has no schema version.")
        where = f"{self.manifest} gives it" if listed else "it has"
        raise self.unknown_version(
            path,
            f"{where} a schema version this version has no reader for. It reads {name}"
            f" {' or '.join(readable)}.",
        )

    def validated[M: BaseModel](self, model: type[M], content: bytes, path: str, what: str) -> M:
        """`content`, the file at `path`, as `model`. `what` names the model in a message, such
        as "run manifest"."""
        try:
            return model.model_validate_json(content)
        except ValidationError as error:
            # Only the model's own fields are named: an unexpected key is text from the file.
            details = error.errors(include_url=False, include_input=False, include_context=False)
            named_fields = sorted(
                {
                    str(detail["loc"][0])
                    for detail in details
                    if detail["loc"] and detail["loc"][0] in model.model_fields
                }
            )
            check = f"check `{'`, `'.join(named_fields)}`" if named_fields else "check its fields"
            raise self.refused(f"{named(path)} isn't a valid {what}: {check}.") from None

    def check_plan_hash(self, plan: Plan | PlanV1_1, file: str) -> None:
        """Checks that `plan` recomputes to its `plan_hash`. `file` names its file in the
        messages, such as "its plan.json"."""
        try:
            recomputed = plan_hash(plan)
        except ValueError as error:
            # The message names the kind of value canonical JSON can't write, never the value.
            raise self.refused(f"{file} can't be hashed ({error}).") from None
        if recomputed != plan.plan_hash:
            raise self.refused(
                f"{file} doesn't recompute to its plan_hash, so the plan changed after it was"
                " approved."
            )

    def table_rows[R](
        self, read: Callable[[bytes, str], tuple[R, ...]], content: bytes, path: str
    ) -> tuple[R, ...]:
        """The rows of the table in `content`, the file at `path`, as `read` reads them."""
        try:
            return read(content, f"its {named(path)}")
        except TrialFolioError as error:
            # The tables' messages name the line and the column, never a value.
            raise self.refused(error.message) from None


def named(path: str) -> str:
    """A path as a message names it: in backticks, with each character that isn't visible
    escaped."""
    return f"`{visible(path)}`"


def artifact_id(content: bytes) -> str:
    """The `artifact_id` of a file that holds `content`: `sha256:` and the hex SHA-256 of its
    bytes."""
    return "sha256:" + sha256_hex(content)


def matches(content: bytes, artifact: ManifestArtifact | ExperimentArtifact) -> bool:
    """Whether `content` has the size and `artifact_id` the manifest's entry records."""
    return len(content) == artifact.size and artifact_id(content) == artifact.artifact_id


def labeled(rows: Iterable[MetricsRow | SettingsRow], case_id: str) -> bool:
    """Whether each row of a case's tables is labeled with its `case_id`."""
    return all(row.label == case_id for row in rows)


def holds_each_metric(rows: Sequence[MetricsRow]) -> bool:
    """Whether `metrics.csv`'s rows are one for each of the layout's metrics, in order, each in
    the metric's unit."""
    return tuple((row.subject, row.metric_id, row.unit) for row in rows) == _METRIC_ROWS


def holds_each_setting(rows: Sequence[SettingsRow], planned: Sequence[PlanSetting]) -> bool:
    """Whether `settings.csv`'s rows are one for each of the plan's settings, in order."""
    return tuple(row.setting for row in rows) == tuple(setting.setting for setting in planned)


def drawn_from(rows: Iterable[MetricsRow | SettingsRow], *sources: str) -> bool:
    """Whether each row was drawn from one of `sources`, by its `artifact_id`."""
    return all(row.source_artifact in sources for row in rows)
