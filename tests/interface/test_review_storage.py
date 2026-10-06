"""A storage failure or an interrupt after `trialfolio review` claims its output directory exits
with `storage.write_failed` and 4, or `command.interrupted` and 130, leaves no review manifest,
and says the review is incomplete. So does an unexpected exception, a defect, with
`internal.unexpected` and 1. A manifest the store published before its write failed is
discarded; one that can't be removed is named, because the review then reads as complete. On Linux
and macOS, a file system without hard links fails at the first copy.

Traces to R02-AC19, and to the parts of R02-AC13 about a failure after the claim: the summary
holds the `review_id`, even when an interrupt comes before the command has recorded the claim, and
counts `differences.csv` once it's written. Also to docs/contracts.md's running the commands: an
unexpected exception after the claim says the review has no manifest, and the command's events
carry the `review_id` from the claim on, `cli.command.unexpected` included. And to its labels in
logs: a failed copy's logged message names its result by its position, while the message on
stderr gives its path. R02-T08 wrote these ahead of R02-T10.

The review runs through the CLI's entry function in the test process, with storage faults
wrapping the real store. A fault named `/manifest.json` is the review's own manifest, and
`manifest.json` the first copy of a run's.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.interface.conftest import Cli, FaultyStores, Outcome
from tests.support.storage_faults import StorageFaults, placeholder_identities
from trialfolio.errors import TrialFolioError
from trialfolio.storage import ArtifactStore, LocalArtifactStore

type Built = Callable[[str], Path]

INCOMPLETE = "The review has no manifest, so it's incomplete."

FAULTS = {
    "copy": "plan.json",
    "differences": "differences.csv",
    "report": "report.html",
    "manifest": "/manifest.json",
}
"""Where a fault strikes: the first run's copied plan, `inputs/hold25/plan.json`, and each of the
review's own files after it."""

LAST_PUBLISHED = {
    "copy": "inputs/hold25/manifest.json",
    "differences": "inputs/hold50/normalized/settings.csv",
    "report": "normalized/differences.csv",
    "manifest": "report.html",
}
"""The file published just before each fault, so the fault strikes the file it names."""

SYNC_FAILED = TrialFolioError(
    "storage.write_failed",
    "Couldn't write manifest.json durably: Input/output error. Check the output directory's free"
    " space and permissions.",
)
"""What the store raises when the sync after publishing a file fails."""


def review(
    cli: Cli, path: Path, out: Path, store_factory: Callable[[str], ArtifactStore]
) -> Outcome:
    cli.accept_license()
    return cli("review", path, "--out", out, "--json", store_factory=store_factory)


def failed(outcome: Outcome, code: str, exit_code: int) -> str:
    """The error's message, once the outcome is checked."""
    assert outcome.exit_code == exit_code, outcome.stderr
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    message = error["message"]
    assert isinstance(message, str)
    assert f"Error ({code}): {message}" in outcome.stderr
    return message


def claimed(outcome: Outcome, out: Path) -> None:
    """The summary of a review that claimed its output directory: its `review_id`, which the
    log's events carry, and the directory as given."""
    summary = outcome.summary
    assert summary["output_dir"] == str(out)
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert list(ids) == ["review_id"]  # pyright: ignore[reportUnknownArgumentType]
    log = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8")
    events = [json.loads(line) for line in log.splitlines()]
    assert events[-1]["event"] == "cli.command.completed"
    assert events[-1]["review_id"] == ids["review_id"]


@pytest.mark.parametrize("at", FAULTS)
def test_a_storage_failure_leaves_no_manifest_and_says_the_review_is_incomplete(
    cli: Cli, built: Built, faults: FaultyStores, at: str
) -> None:
    out = cli.tmp / "review"
    faults.fail_os(FAULTS[at])

    outcome = review(cli, built("example.yaml"), out, faults)

    message = failed(outcome, "storage.write_failed", 4)
    assert INCOMPLETE in message
    assert faults.published[-1] == LAST_PUBLISHED[at]
    assert not (out / "manifest.json").exists()
    assert "manifest" not in outcome.summary["outputs"]  # pyright: ignore[reportOperatorIssue]
    claimed(outcome, out)
    # Each file is written once, and nothing after the failure.
    assert len(faults.published) == len(set(faults.published))


@pytest.mark.parametrize("at", FAULTS)
def test_an_interrupt_leaves_no_manifest_and_says_the_review_is_incomplete(
    cli: Cli, built: Built, faults: FaultyStores, at: str
) -> None:
    out = cli.tmp / "review"
    faults.fail_before(FAULTS[at], KeyboardInterrupt())

    outcome = review(cli, built("example.yaml"), out, faults)

    message = failed(outcome, "command.interrupted", 130)
    assert message.startswith("Trial Folio was interrupted.")
    assert INCOMPLETE in message
    assert faults.published[-1] == LAST_PUBLISHED[at]
    assert not (out / "manifest.json").exists()
    claimed(outcome, out)


def test_an_interrupt_before_the_command_records_the_claim_still_names_the_review(
    cli: Cli, built: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ctrl-C can arrive once the review has claimed its directory, before the command has
    # recorded the claim, which starts its log there. Nothing at a boundary runs in between, so
    # the interrupt is raised as the command's callback starts. The runs are built first, with
    # the callback as it is.
    path = built("example.yaml")

    def interrupted(*_: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("trialfolio.cli._Invocation.claimed", interrupted)
    out = cli.tmp / "review"

    outcome = review(cli, path, out, LocalArtifactStore)

    message = failed(outcome, "command.interrupted", 130)
    assert INCOMPLETE in message
    assert sorted(path.name for path in out.iterdir()) == ["configuration.yaml"]
    # The summary still names the directory the review claimed, with its review_id.
    summary = outcome.summary
    assert summary["output_dir"] == str(out)
    ids = summary["ids"]
    assert isinstance(ids, dict)
    assert list(ids) == ["review_id"]  # pyright: ignore[reportUnknownArgumentType]


@pytest.mark.parametrize("published", [False, True], ids=["report", "published-manifest"])
def test_an_unexpected_exception_leaves_no_manifest_and_says_the_review_is_incomplete(
    cli: Cli, built: Built, faults: FaultyStores, published: bool
) -> None:
    out = cli.tmp / "review"
    defect = RuntimeError("its own message")
    if published:
        # Raised once the store has published the manifest, which the review then discards.
        faults.fail_after("/manifest.json", defect)
    else:
        faults.fail_before("report.html", defect)

    outcome = review(cli, built("example.yaml"), out, faults)

    message = failed(outcome, "internal.unexpected", 1)
    assert message.startswith("Trial Folio failed unexpectedly (RuntimeError).")
    assert INCOMPLETE in message
    assert "its own message" not in message
    assert faults.published[-1] == ("manifest.json" if published else "normalized/differences.csv")
    assert not (out / "manifest.json").exists()
    claimed(outcome, out)
    log = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8")
    (unexpected,) = (
        event
        for event in (json.loads(line) for line in log.splitlines())
        if event["event"] == "cli.command.unexpected"
    )
    assert unexpected["review_id"] == outcome.summary["ids"]["review_id"]  # pyright: ignore[reportIndexIssue]
    assert "its own message" not in log


def test_a_failed_copy_is_named_by_its_path_on_stderr_and_by_its_position_in_the_log(
    cli: Cli, built: Built, faults: FaultyStores
) -> None:
    out = cli.tmp / "review"
    faults.fail_os("settings.csv")  # The first run's, hold25's, the baseline's.

    outcome = review(cli, built("example.yaml"), out, faults)

    message = failed(outcome, "storage.write_failed", 4)
    assert message.startswith("Couldn't write inputs/hold25/normalized/settings.csv durably:")
    log = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8")
    (ended,) = (
        json.loads(line)["message"]
        for line in log.splitlines()
        if json.loads(line)["event"] == "cli.command.completed"
    )
    assert "Couldn't write normalized/settings.csv of result 1 durably:" in ended
    assert "hold25" not in log


def test_a_failure_after_the_manifest_is_published_discards_it(
    cli: Cli, built: Built, faults: FaultyStores
) -> None:
    out = cli.tmp / "review"
    faults.fail_after("/manifest.json", SYNC_FAILED)

    outcome = review(cli, built("example.yaml"), out, faults)

    message = failed(outcome, "storage.write_failed", 4)
    assert faults.published[-1] == "manifest.json"
    assert not (out / "manifest.json").exists()
    assert INCOMPLETE in message
    claimed(outcome, out)


class _Undiscardable(StorageFaults):
    """Storage faults whose store can't remove a file."""

    def discard(self, path: str, data: bytes) -> None:
        raise TrialFolioError("storage.write_failed", f"Couldn't remove {path}.")


def test_a_published_manifest_that_cant_be_discarded_is_named(
    cli: Cli, built: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = cli.tmp / "review"

    def undiscardable(root: str) -> ArtifactStore:
        store = _Undiscardable(LocalArtifactStore(root), monkeypatch)
        store.fail_after("/manifest.json", SYNC_FAILED)
        return store

    outcome = review(cli, built("example.yaml"), out, undiscardable)

    message = failed(outcome, "storage.write_failed", 4)
    assert (out / "manifest.json").exists()
    assert "manifest" not in outcome.summary["outputs"]  # pyright: ignore[reportOperatorIssue]
    assert (
        "The review's manifest.json was published before the failure, and couldn't be removed,"
        " so the review reads as complete although the command failed."
    ) in message


@pytest.mark.skipif(sys.platform == "win32", reason="Windows publishes files by renaming them")
@pytest.mark.parametrize("placeholder", [False, True], ids=["own-identity", "placeholder-identity"])
def test_a_file_system_without_hard_links_fails_at_the_first_copy(
    cli: Cli, built: Built, faults: FaultyStores, monkeypatch: pytest.MonkeyPatch, placeholder: bool
) -> None:
    if placeholder:
        # FAT and exFAT on macOS also give each new, empty file a temporary inode until its
        # first write.
        placeholder_identities(monkeypatch)
    path = built("example.yaml")
    out = cli.tmp / "review"
    faults.fail_link("manifest.json")  # The first copy, inputs/hold25/manifest.json.

    outcome = review(cli, path, out, faults)

    message = failed(outcome, "storage.write_failed", 4)
    assert message.startswith("Couldn't write inputs/hold25/manifest.json:")
    assert "doesn't support hard links" in message
    assert INCOMPLETE in message
    # The claim's configuration is the only file left, with the log the claim started, and no
    # temporary file.
    files = sorted(path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file())
    assert files == ["configuration.yaml", "logs/trialfolio.log"]


# The summary's counts once differences.csv is written (R02-AC13)


@pytest.mark.parametrize(
    ("at", "written"),
    [("plan.json", False), ("report.html", True), ("/manifest.json", True)],
    ids=["copy", "report", "manifest"],
)
def test_the_summary_counts_the_table_once_it_is_written(
    cli: Cli, built: Built, faults: FaultyStores, at: str, written: bool
) -> None:
    # undeclared.yaml has three undeclared critical changes, and missing-metrics.json's three
    # missing metrics.
    out = cli.tmp / "review"
    faults.fail_os(at)

    outcome = review(cli, built("undeclared.yaml"), out, faults)

    failed(outcome, "storage.write_failed", 4)
    counts = outcome.summary["counts"]
    assert counts == {  # pyright: ignore[reportUnknownMemberType]
        "results": 4,
        "settings_flagged": 3 if written else 0,
        "metrics_unavailable": 3 if written else 0,
        "warnings": 0,
    }
    outputs = outcome.summary["outputs"]
    expected = {"differences": "normalized/differences.csv"} if written else {}
    if at == "/manifest.json":
        expected["report"] = "report.html"
    assert outputs == expected
