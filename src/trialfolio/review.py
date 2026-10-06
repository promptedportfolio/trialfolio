"""Writing a review into a new output directory: the steps of `trialfolio review` after the input
check has read and checked each result's run (release 0.2.0, R02-T08; docs/contracts.md, review
output).

`Review.write`:

1. Claims the output directory with `configuration.yaml`, the review configuration's bytes
   (`output.not_empty`). Nothing is written before.
2. Writes each result's copies, in the configuration's order, under `inputs/<label>/`: its run's
   `manifest.json`, `plan.json`, and then its tables, from the bytes the input check read. The
   first is the first atomic write, so a file system that can't take one fails there
   (`storage.write_failed`).
3. Compares each result with the baseline, warns when results share a saved response, and writes
   `normalized/differences.csv`.
4. Writes `report.html`, rendered from what the manifest will record, without the report.
5. Writes `manifest.json` last. Without it, the review is incomplete. A write of it that fails, an
   interrupt included, discards it if the store had published it already, so a review the
   command reports as failed never reads as complete.

A failure or an interrupt after the claim leaves no manifest, and its message says the review is
incomplete. Labels are configuration values, which logs never hold, so the store logs each copy,
and names it in its errors' logged messages, by its result's position, such as `plan.json of
result 2`, and the warning names results by their positions too. Nothing here prompts, reads the
environment, or sends anything.
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Final

from trialfolio.attempts import Clock, utc_now
from trialfolio.contracts.manifest import SourceRecord
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.review_manifest import (
    REVIEW_CONFIGURATION_FORMAT,
    Method,
    ReviewArtifact,
    ReviewArtifactRole,
    ReviewCapabilities,
    ReviewCommandRecord,
    ReviewManifest,
    ReviewManifestCounts,
)
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.differences import (
    DIFFERENCES_PATH,
    METHOD,
    METHOD_VERSION,
    ComparedRun,
    Differences,
    SharedResponse,
    compare,
)
from trialfolio.errors import TrialFolioError
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.report import HtmlReportRenderer, ReviewEvidence, write_review_report
from trialfolio.review_inputs import ReviewInput
from trialfolio.runs import CONFIGURATION_PATH, MANIFEST_PATH
from trialfolio.storage import ArtifactStore, StoredFile
from trialfolio.tables import differences_csv

_logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the review manifests this module writes."""

INPUTS_DIRECTORY: Final = "inputs"
"""The directory that holds each result's copies, under its label."""


class Review:
    """One review of the checked runs `inputs`, written into the output directory of `store`.

    Its properties stay readable whatever happens, so a command interrupted while it writes still
    knows what it wrote: whether it claimed the directory, `differences.csv`, the report, and the
    manifest.
    """

    def __init__(
        self,
        configuration: ReviewConfiguration,
        content: bytes,
        inputs: Sequence[ReviewInput],
        store: ArtifactStore,
        command: ReviewCommandRecord,
        *,
        trialfolio_version: str,
        clock: Clock = utc_now,
    ) -> None:
        """Writes nothing. `content` is the review configuration file's bytes, as `configuration`
        was read from them, and `inputs` each result's run, as the input check read it, in the
        configuration's order. The review gets a new random `review_id`.

        Raises `ValueError` unless `inputs` holds one run for each result, in order.
        """
        labels = tuple(result.label for result in configuration.results)
        if tuple(checked.result.label for checked in inputs) != labels:
            raise ValueError("each result has one input, in the configuration's order")
        self._configuration = configuration
        self._content = content
        self._inputs = tuple(inputs)
        self._store = store
        self._command = command
        self._version = trialfolio_version
        self._clock = clock
        self._review_id = uuid.uuid4()
        self._claimed = False
        self._artifacts: list[ReviewArtifact] = []
        self._differences: Differences | None = None
        self._differences_file: StoredFile | None = None
        self._report: StoredFile | None = None
        self._manifest: StoredFile | None = None
        self._manifest_left = False
        """Whether a manifest whose write failed couldn't be discarded."""

    @property
    def review_id(self) -> uuid.UUID:
        return self._review_id

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed. Before then, nothing was written."""
        return self._claimed

    @property
    def synthetic(self) -> bool:
        """Whether any result is synthetic: the run `trialfolio demo` writes."""
        return any(checked.reviewed.synthetic for checked in self._inputs)

    @property
    def differences(self) -> Differences | None:
        """The comparison, once `differences.csv` is written."""
        return self._differences

    @property
    def differences_file(self) -> StoredFile | None:
        return self._differences_file

    @property
    def report(self) -> StoredFile | None:
        return self._report

    @property
    def manifest(self) -> StoredFile | None:
        """The manifest, once it's written: the review is then complete."""
        return self._manifest

    def write(self, *, on_claimed: Callable[[], object] | None = None) -> TrialFolioError | None:
        """Takes the steps the module lists. `on_claimed` is called once the directory is
        claimed, before anything else is written into it, such as to start writing logs there.

        Returns the error the command reports, or None when the review completed. Raises the
        claim's `TrialFolioError`, `output.not_empty` or `storage.write_failed`, and a
        `KeyboardInterrupt` during the claim, which removes what the claim created, so nothing
        is left. After the claim, a storage failure or an interrupt is returned, and its message
        says the review is incomplete. An unexpected exception after the claim leaves the
        review without a manifest too, and `ending_detail` says what it means for the review.
        """
        if self._claimed:
            raise RuntimeError("a review is written once")
        configuration = self._store.claim(CONFIGURATION_PATH, self._content)
        self._claimed = True
        self._artifacts.append(self._listed_configuration(configuration))
        try:
            if on_claimed is not None:
                on_claimed()
            self._copy()
            differences = compare(
                self._configuration.baseline,
                [ComparedRun.of(checked) for checked in self._inputs],
            )
            for shared in differences.shared_responses:
                self._warn_shared(shared)
            self._write_differences(differences)
            evidence = ReviewEvidence(
                self._configuration,
                self._inputs,
                differences,
                self._review_id,
                self._command.started_at,
                tuple(self._artifacts),
            )
            self._report = write_review_report(
                self._store, evidence, HtmlReportRenderer(self._version)
            )
            self._artifacts.append(_listed(self._report, "report", None))
            self._write_manifest(self._build_manifest(differences, self._clock()))
        except KeyboardInterrupt:
            return TrialFolioError(
                "command.interrupted", f"Trial Folio was interrupted. {self.ending_detail()}"
            )
        except TrialFolioError as failure:
            if failure.code != "storage.write_failed":
                raise
            ending = self.ending_detail()
            return TrialFolioError(
                failure.code, f"{failure.message} {ending}", f"{failure.log_message} {ending}"
            )
        return None

    def ending_detail(self) -> str:
        """What the review's files say, for the message of an ending after the claim: whether
        the review has its manifest, and so whether it reads as complete."""
        if self._manifest is not None:
            return "The review's manifest was written, so the review is complete."
        if self._manifest_left:
            return (
                "The review's manifest.json was published before the failure, and couldn't be"
                " removed, so the review reads as complete although the command failed. Remove"
                " its output directory, and run the review again."
            )
        return (
            "The review has no manifest, so it's incomplete. Remove its output directory, or"
            " choose another, and run the review again."
        )

    def _log_fields(self, event: str) -> dict[str, str]:
        return {"event": event, "review_id": str(self._review_id)}

    def _copy(self) -> None:
        """Writes each result's copies, from the bytes the input check read."""
        for checked in self._inputs:
            label = checked.result.label
            for copy in checked.copies:
                stored = self._store.write(
                    f"{INPUTS_DIRECTORY}/{label}/{copy.path}",
                    copy.content,
                    # The path holds the label, which logs never hold.
                    logged_as=f"{copy.path} of result {checked.position}",
                )
                self._artifacts.append(_listed(stored, copy.role, copy.schema_version, label=label))

    def _warn_shared(self, shared: SharedResponse) -> None:
        _logger.warning(
            "Results %s have byte-identical saved responses, so their metrics come from one"
            " response. differences.csv flags the metric rows of each that isn't the baseline"
            " identical_source, and the report names them.",
            _series(shared.positions),
            extra=self._log_fields("review.response.shared"),
        )

    def _write_differences(self, differences: Differences) -> None:
        stored = self._store.write(DIFFERENCES_PATH, differences_csv(differences.rows))
        self._differences, self._differences_file = differences, stored
        self._artifacts.append(_listed(stored, "differences", TABLES_SCHEMA_VERSION))

    def _write_manifest(self, manifest: ReviewManifest) -> None:
        """Writes the manifest. A write that fails, an interrupt or an unexpected exception
        included, discards the file if the store published it before the failure."""
        data = (manifest.model_dump_json(indent=2) + "\n").encode("utf-8")
        try:
            self._manifest = self._store.write(MANIFEST_PATH, data)
        except BaseException:
            self._manifest = None
            try:
                self._store.discard(MANIFEST_PATH, data)
            except TrialFolioError:
                self._manifest_left = True
            raise

    def _listed_configuration(self, stored: StoredFile) -> ReviewArtifact:
        version = self._configuration.schema_version
        return _listed(
            stored,
            "configuration",
            version,
            source=SourceRecord(
                acquired_at=self._command.started_at,
                format=REVIEW_CONFIGURATION_FORMAT,
                format_version=version,
                parser_version=None,
                provenance="user_supplied",
                operation=None,
            ),
        )

    def _build_manifest(self, differences: Differences, created_at: datetime) -> ReviewManifest:
        return ReviewManifest(
            schema_version=SCHEMA_VERSION,
            artifact_type="review",
            trialfolio_version=self._version,
            created_at=created_at,
            review_id=self._review_id,
            command=self._command,
            synthetic=self.synthetic,
            outcome="completed",
            error=None,
            baseline=self._configuration.baseline,
            results=tuple(checked.reviewed for checked in self._inputs),
            artifacts=tuple(self._artifacts),
            methods=(Method(name=METHOD, version=METHOD_VERSION),),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=ReviewCapabilities(
                return_series="absent",
                statistical_validation="not_assessed",
                trading_readiness="not_assessed",
            ),
            counts=ReviewManifestCounts(
                results=len(self._inputs),
                settings=differences.setting_counts,
                metrics=differences.metric_counts,
            ),
        )


def _listed(
    stored: StoredFile,
    role: ReviewArtifactRole,
    schema_version: str | None,
    *,
    label: str | None = None,
    source: SourceRecord | None = None,
) -> ReviewArtifact:
    return ReviewArtifact(
        path=stored.path,
        artifact_id=stored.artifact_id,
        size=stored.size,
        role=role,
        schema_version=schema_version,
        source=source,
        label=label,
    )


def _series(positions: Sequence[int]) -> str:
    """Positions as a sentence lists them: `1 and 2`, or `1, 2, and 3`."""
    items = [str(position) for position in positions]
    if len(items) < 3:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"
