"""The review's input check: each result's run read and checked, in the configuration's order,
before anything is written (release 0.2.0, R02-T05; docs/contracts.md, review output).

A result's `run` path names its run's directory, relative to the review configuration's
directory unless it's absolute, as every configuration's file paths are. The check:

- refuses a path where nothing exists with `input.not_found`, as `trialfolio report` does. The
  file system resolves the path, so a `..` after a symbolic link leads where opening it would.
- reads each run once, through an `ArtifactStore`, and checks it's a complete run, as
  `trialfolio report` does (`check_run`): `input.not_a_run`, or `artifact.unknown_schema_version`
  for a schema version with no reader.
- keeps the bytes it checked of the files a review copies: the run's manifest, its plan, and its
  normalized tables, when it has them. The review writes its copies from those bytes, never by
  reading the run again, so a file changed after the check can't be copied.
- works out what the review manifest's `results` say each label names.

The first result that fails is reported. Its message names the result by its label, and its run
directory as the configuration gives it. Labels and paths are configuration values, which logs
never hold, so the logged message, and the check's log events, name the result by its position
in `results` instead, such as "result 2".
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from trialfolio.canonical import sha256_hex
from trialfolio.contracts.review_configuration import ReviewConfiguration, ReviewResult
from trialfolio.contracts.review_manifest import ReviewArtifactRole, ReviewedResult
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError
from trialfolio.runs import MANIFEST_PATH, CheckedRun, RunName, SavedRun, check_run, not_a_run
from trialfolio.storage import ArtifactStore, LocalArtifactStore

_logger = logging.getLogger(__name__)

_COPIED_ROLES: Final[tuple[ReviewArtifactRole, ...]] = ("plan", "metrics", "settings")
"""The roles of the files listed in a run's manifest that a review copies, in the order it
copies them, after the manifest itself."""

type RunStores = Callable[[str], ArtifactStore | None]
"""The store of the run directory a result's `run` path names, or None when nothing exists
there."""


@dataclass(frozen=True)
class RunCopy:
    """A file of a run that a review copies, byte for byte, under `inputs/<label>/`."""

    path: str
    """Its path in the run."""
    role: ReviewArtifactRole
    schema_version: str
    """The one the run records: the manifest's own, and for any other file, its manifest
    entry's."""
    content: bytes
    """The bytes the check read and checked."""

    @property
    def artifact_id(self) -> str:
        return "sha256:" + sha256_hex(self.content)

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class ReviewInput:
    """One result's run, read and checked."""

    position: int
    """The result's position in `results`, from 1, as logs name it."""
    result: ReviewResult
    run: SavedRun
    copies: tuple[RunCopy, ...]
    """In the order the review writes them: `manifest.json`, `plan.json`, and then the tables,
    when the run has them."""
    reviewed: ReviewedResult
    """What the review manifest's `results` say the result's label names."""


def local_run_stores(configuration_path: str | os.PathLike[str]) -> RunStores:
    """The runs a review configuration at `configuration_path` names, on the local file system:
    each `run` path is read from the configuration's directory, unless it's absolute."""
    directory = Path(configuration_path).parent

    def store(run: str) -> ArtifactStore | None:
        # The path the file system resolves, which both finds the run and reads it. A `..` after
        # a symbolic link leads to the parent of the link's target, as opening the path does,
        # not where the store's abspath would lead, by removing it with the segment before it.
        try:
            path = os.path.realpath(directory / run, strict=True)
        except OSError:
            # Nothing exists there, a link leads to nothing, or a part can't be read.
            return None
        return LocalArtifactStore(path)

    return store


def check_review_inputs(
    configuration: ReviewConfiguration, run_stores: RunStores
) -> tuple[ReviewInput, ...]:
    """Reads and checks each result's run, in the configuration's order. Writes nothing.

    Raises `TrialFolioError` for the first result whose run fails: with `input.not_found` when
    nothing exists at its `run` path, `input.not_a_run` when it isn't a complete run, or one a
    review can't copy, and `artifact.unknown_schema_version` when one of its artifacts has a
    schema version with no reader.
    """
    return tuple(
        _check(position, result, run_stores)
        for position, result in enumerate(configuration.results, start=1)
    )


def _check(position: int, result: ReviewResult, run_stores: RunStores) -> ReviewInput:
    name = RunName(
        shown=f"result `{result.label}`'s run directory (`{visible(result.run)}`)",
        logged=f"result {position}'s run directory",
    )
    store = run_stores(result.run)
    if store is None:
        raise TrialFolioError(
            "input.not_found", _doesnt_exist(name.shown), _doesnt_exist(name.logged)
        )
    checked = check_run(store, name)
    copies = _copies(checked, name)
    saved = checked.saved
    reviewed = ReviewedResult(
        label=result.label,
        run_manifest=copies[0].artifact_id,
        synthetic=saved.manifest.synthetic,
        plan_hash=saved.plan.plan_hash,
        case_id=saved.plan.cases[0].case_id,
        normalized_tables=saved.metrics is not None,
        response=_response(saved, name),
    )
    _logger.info(
        "Checked result %d's run, %s.",
        position,
        reviewed.run_manifest,
        extra={
            "event": "review.input.loaded",
            "plan_hash": reviewed.plan_hash,
            "case_id": reviewed.case_id,
        },
    )
    return ReviewInput(position, result, saved, copies, reviewed)


def _doesnt_exist(run: str) -> str:
    return (
        f"{run[:1].upper()}{run[1:]} doesn't exist. A `run` path is read from the review"
        " configuration's directory, unless it's absolute. Give the output directory of a run"
        " that trialfolio run or trialfolio demo wrote. Nothing was written."
    )


def _copies(checked: CheckedRun, name: RunName) -> tuple[RunCopy, ...]:
    manifest = checked.saved.manifest
    copies = [
        RunCopy(
            MANIFEST_PATH, "run_manifest", manifest.schema_version, checked.contents[MANIFEST_PATH]
        )
    ]
    listed = {artifact.role: artifact for artifact in manifest.artifacts}
    for role in _COPIED_ROLES:
        # The check found the plan listed once, and both tables or neither, each once.
        artifact = listed.get(role)
        if artifact is None:
            continue
        if artifact.schema_version is None:
            raise not_a_run(
                name,
                f"its manifest lists `{artifact.path}` without a schema version, which a review"
                " records for each file it copies.",
            )
        copies.append(
            RunCopy(artifact.path, role, artifact.schema_version, checked.contents[artifact.path])
        )
    return tuple(copies)


def _response(run: SavedRun, name: RunName) -> str | None:
    """The `artifact_id` of the run's saved response, or None when it has none."""
    responses = [
        attempt.record.response.artifact_id
        for attempt in run.attempts
        if attempt.record is not None and attempt.record.response is not None
    ]
    if len(responses) > 1:
        raise not_a_run(
            name,
            "its attempts saved more than one response, but a screen run sends its request at"
            " most once.",
        )
    return responses[0] if responses else None
