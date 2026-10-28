"""`trialfolio run` with a changed configuration, into its experiment's directory: a revision needs
`--revision-reason` and the approval of its hash, or the command fails with `plan.changed`; an
approved one records its plan, keeps each case whose settings didn't change, and retires the
others; a reason with no revision fails, unless it's the current plan's own; and another
experiment isn't a revision.

Traces to R03-AC07's interface part, R03-AC03's revision part (each plan's `experiment.json`
records the plans before it unchanged, and the revision's reason and changes: `purpose` for
`purpose-changed.yaml`, the added and retired cases for `holdings-40.yaml`, the retired case, as
the plan before it held it, for `variant-removed.yaml`, and both versions for a change of
versions alone), and to docs/contracts.md, experiment plans and revisions (approving a revision,
the plan display of a revision, and a change of versions). R03-T13 wrote them. R03-T11 added
R03-AC03's checks of the earlier entries and the reason to the revisions that keep every case,
to `variant-removed.yaml`'s, with its retired case, and to a change of versions; and R03-AC07's
check that a new order of one setting's variants keeps every case. Each test writes
`example.yaml`'s experiment, or `two-holdings.yaml`'s, with the experiment builder, then runs a
revision of it, from `experiment-configs/revisions/`, through the CLI's entry function in the
test process, over the fake server; the package versions double reports another version of Trial
Folio for a first run, and the terminal is a real pseudo-terminal in the test process.
"""

import sys
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.directories import snapshot
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.package_versions import fake_distribution
from tests.support.paths import screen_config
from tests.support.saved_records import session_manifest
from tests.support.terminal import PseudoTerminal
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.experiment_configuration import ExperimentConfiguration
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_record import ExperimentRecord, VersionChange
from trialfolio.planning import build_experiment_plan, installed_versions

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

EXAMPLE = experiment_config("example.yaml")
REASON = "Tries 40 holdings instead of 50."

type Builder = ExperimentBuilder[Outcome]


def revision(name: str) -> Path:
    return experiment_config(f"revisions/{name}")


def record(out: Path, plan: int) -> ExperimentRecord:
    return ExperimentRecord.model_validate_json(
        (out / f"plans/{plan}/experiment.json").read_bytes()
    )


def completed(cli: Cli, experiments: Builder, path: Path = EXAMPLE) -> Path:
    """Writes the experiment `path` gives, every case succeeding, and returns its directory."""
    cli.ready()
    out = cli.tmp / "experiment"
    cases = len(build_experiment_plan(read(path), installed_versions()).cases)
    outcome = experiments.run(path, out, sends=[returns() for _ in range(cases)])
    assert outcome.exit_code == 0, outcome.stderr
    return out


def read(path: Path) -> ExperimentConfiguration:
    return read_experiment_configuration(path.read_bytes(), str(path))


# Without both a reason and the revision's hash, plan.changed


@pytest.mark.parametrize(
    "given",
    [
        pytest.param("neither", id="no-reason-or-approve"),
        pytest.param("reason", id="reason-alone"),
        pytest.param("approve", id="approve-alone"),
        pytest.param("current-hash", id="reason-and-the-current-plans-hash"),
    ],
)
def test_a_revision_without_its_reason_and_its_hash_fails_and_writes_nothing(
    cli: Cli, experiments: Builder, given: str
) -> None:
    out = completed(cli, experiments)
    changed = revision("holdings-40.yaml")
    revised = plan_hash(changed, out)
    current = plan_hash(EXAMPLE, out)
    options = {
        "neither": [],
        "reason": ["--revision-reason", REASON],
        "approve": ["--approve", revised],
        "current-hash": ["--revision-reason", REASON, "--approve", current],
    }[given]
    before = snapshot(out)
    received = len(cli.server.received)

    outcome = experiments.run(changed, out, *options, approve=False)

    assert outcome.exit_code == 3, outcome.stderr
    error = outcome.error
    assert error["code"] == "plan.changed"
    assert f"--approve {revised}" in error["message"]
    assert "--revision-reason" in error["message"]
    assert "changed since the experiment's current plan, plan 1" in error["message"]
    assert snapshot(out) == before
    assert len(cli.server.received) == received
    summary = outcome.summary
    assert summary["output_dir"] is None
    assert outcome.ids["plan_hash"] == revised
    # The cases the revision would hold: the new holdings-50 case not yet run, and the old one
    # counted as retired.
    cases = outcome.cases
    assert [case["outcome"] for case in cases] == [
        "succeeded",
        "succeeded",
        "not_yet_run",
        "succeeded",
        "succeeded",
    ]
    counts = outcome.counts
    assert (counts["cases_retired"], counts["attempts"]) == (1, 5)


def test_an_approved_revision_sends_only_its_new_case_and_keeps_the_retired_one(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    first = record(out, 1)
    old = next(case for case in first.planned_cases if case.case_key == "holdings-50")
    received = len(cli.server.received)

    outcome = experiments.run(
        revision("holdings-40.yaml"), out, "--revision-reason", REASON, sends=[returns()]
    )

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests()[received:] == ["POST /auth", "POST /screen/backtest"]
    second = record(out, 2)
    new = next(case for case in second.planned_cases if case.case_key == "holdings-50")
    assert new.case_id != old.case_id
    assert (out / "cases" / old.case_id / "attempts").is_dir()
    # The entries before the last are the first plan's, unchanged (R03-AC03).
    assert second.plans[:-1] == first.plans
    entry = second.plans[-1]
    assert (entry.plan, entry.revises, entry.reason, entry.approval) == (
        2,
        first.plans[0].plan_hash,
        REASON,
        "option",
    )
    assert entry.changes is not None
    assert [(c.case_id, c.case_key) for c in entry.changes.cases_added] == [
        (new.case_id, "holdings-50")
    ]
    assert [(c.case_id, c.case_key) for c in entry.changes.cases_retired] == [
        (old.case_id, "holdings-50")
    ]
    (retired,) = second.retired_cases
    assert (retired.case_id, retired.case_key, retired.plan) == (old.case_id, "holdings-50", 1)
    assert (retired.description, retired.variant) == (old.description, old.variant)
    counts = session_manifest(out, 2, ExperimentManifest).counts
    assert (counts.retired_cases, counts.attempts.succeeded, counts.cases.succeeded) == (1, 6, 5)
    assert outcome.counts["cases_retired"] == 1
    assert outcome.summary["output_dir"] == str(out)


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("key-renamed.yaml", ("case_keys",)),
        ("description-changed.yaml", ("case_descriptions",)),
        ("purpose-changed.yaml", ("purpose",)),
        ("prior-research-changed.yaml", ("prior_research",)),
        ("budget-raised.yaml", ("budget",)),
        ("default-explicit.yaml", ("case_variants",)),
    ],
)
def test_a_revision_that_keeps_every_case_sends_nothing(
    cli: Cli, experiments: Builder, name: str, parts: tuple[str, ...]
) -> None:
    out = completed(cli, experiments)
    received = len(cli.server.received)

    outcome = experiments.run(revision(name), out, "--revision-reason", f"Changes {name}.")

    assert outcome.exit_code == 0, outcome.stderr
    assert len(cli.server.received) == received
    first, second = record(out, 1), record(out, 2)
    assert [case.case_id for case in second.planned_cases] == [
        case.case_id for case in first.planned_cases
    ]
    # The entries before the last are the first plan's, unchanged, and the last has the reason
    # as given, and the part changed alone (R03-AC03).
    assert second.plans[:-1] == first.plans
    assert second.plans[-1].reason == f"Changes {name}."
    changes = second.plans[-1].changes
    assert changes is not None
    assert (changes.versions, changes.parts, changes.cases_added, changes.cases_retired) == (
        (),
        parts,
        (),
        (),
    )
    assert session_manifest(out, 2, ExperimentManifest).counts.cases.succeeded == 5


def test_reordering_one_settings_variants_is_a_revision_that_keeps_every_case(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments, revision("two-holdings.yaml"))
    received = len(cli.server.received)

    outcome = experiments.run(
        revision("two-holdings-reordered.yaml"), out, "--revision-reason", "Reorders them."
    )

    assert outcome.exit_code == 0, outcome.stderr
    assert len(cli.server.received) == received
    first, second = record(out, 1), record(out, 2)
    changes = second.plans[-1].changes
    assert changes is not None
    assert changes.parts == ("case_order",)
    # Every case is kept, in another order (R03-AC07).
    assert (changes.cases_added, changes.cases_retired) == ((), ())
    assert [case.case_id for case in second.planned_cases] != [
        case.case_id for case in first.planned_cases
    ]
    assert sorted(case.case_id for case in second.planned_cases) == sorted(
        case.case_id for case in first.planned_cases
    )
    assert session_manifest(out, 2, ExperimentManifest).counts.cases.succeeded == 6


def test_a_removed_variant_is_retired_and_planning_it_again_brings_it_back_unsent(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    slippage = next(
        case for case in record(out, 1).planned_cases if case.case_key == "slippage-050"
    )
    received = len(cli.server.received)

    removed = experiments.run(
        revision("variant-removed.yaml"), out, "--revision-reason", "Drops slippage."
    )
    again = experiments.run(EXAMPLE, out, "--revision-reason", "Brings slippage back.")

    assert (removed.exit_code, again.exit_code) == (0, 0), again.stderr
    assert len(cli.server.received) == received
    # Each revision's entries before the last are the previous plan's, unchanged, and the last
    # has the reason as given, and the case retired, which the retired cases list as the first
    # plan held it (R03-AC03).
    second = record(out, 2)
    assert second.plans[:-1] == record(out, 1).plans
    entry = second.plans[-1]
    assert entry.reason == "Drops slippage."
    assert entry.changes is not None
    assert [(c.case_id, c.case_key) for c in entry.changes.cases_retired] == [
        (slippage.case_id, "slippage-050")
    ]
    assert (entry.changes.versions, entry.changes.cases_added, entry.changes.parts) == ((), (), ())
    (retired,) = second.retired_cases
    assert (retired.case_id, retired.case_key, retired.plan) == (
        slippage.case_id,
        "slippage-050",
        1,
    )
    assert (retired.description, retired.variant) == (slippage.description, slippage.variant)
    assert retired.variant is not None
    assert (retired.variant.setting, retired.variant.value) == ("slippage_percent", "0.5")
    assert session_manifest(out, 2, ExperimentManifest).counts.retired_cases == 1
    third = record(out, 3)
    assert third.plans[:-1] == second.plans
    assert third.plans[-1].reason == "Brings slippage back."
    assert third.retired_cases == ()
    changes = third.plans[-1].changes
    assert changes is not None
    assert [case.case_id for case in changes.cases_added] == [slippage.case_id]
    counts = session_manifest(out, 3, ExperimentManifest).counts
    assert (counts.cases.succeeded, counts.retired_cases, counts.attempts.succeeded) == (5, 0, 5)


# A reason without a revision


def test_a_reason_with_a_new_experiment_fails_and_creates_nothing(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli(
        "run",
        EXAMPLE,
        "--out",
        out,
        "--approve",
        plan_hash(EXAMPLE, out),
        "--revision-reason",
        REASON,
        "--json",
    )

    assert outcome.exit_code == 2
    error = outcome.error
    assert error["code"] == "plan.approval_required"
    assert (
        "A new experiment has no plan to revise. Run the command without --revision-reason."
        in error["message"]
    )
    assert not out.exists()
    assert cli.server.requests() == []


def test_a_reason_with_a_screen_fails_and_creates_nothing(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "run"

    outcome = cli(
        "run", screen_config("formula.yaml"), "--out", out, "--revision-reason", REASON, "--json"
    )

    assert outcome.exit_code == 2
    error = outcome.error
    assert error["code"] == "plan.approval_required"
    assert "--revision-reason applies only to an experiment's configuration" in error["message"]
    assert not out.exists()
    assert cli.server.requests() == []


def test_a_reason_with_the_current_plan_fails_unless_its_the_reason_the_plan_recorded(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    changed = revision("holdings-40.yaml")
    assert (
        experiments.run(changed, out, "--revision-reason", REASON, sends=[returns()]).exit_code == 0
    )
    before = snapshot(out)
    received = len(cli.server.received)

    other = experiments.run(changed, out, "--revision-reason", "Another reason.")
    assert other.exit_code == 2
    assert other.error["code"] == "plan.approval_required"
    assert (
        "If you changed the configuration, check that this is the file you changed."
        in (other.error["message"])
    )
    assert snapshot(out) == before

    # The command that approved the revision, run again, resumes it.
    same = experiments.run(changed, out, "--revision-reason", REASON)

    assert same.exit_code == 0, same.stderr
    assert len(cli.server.received) == received
    assert (out / "sessions/3/manifest.json").is_file()
    assert not (out / "plans/3").exists()


# Another experiment


@pytest.mark.parametrize("name", ["other-experiment-id.yaml", "other-universe.yaml"])
def test_another_experiment_id_or_universe_is_another_experiment(
    cli: Cli, experiments: Builder, name: str
) -> None:
    out = completed(cli, experiments)
    before = snapshot(out)
    received = len(cli.server.received)

    outcome = cli("run", revision(name), "--out", out, "--revision-reason", REASON, "--json")

    assert outcome.exit_code == 4
    error = outcome.error
    assert error["code"] == "output.not_empty"
    assert "another experiment" in error["message"]
    assert snapshot(out) == before
    assert len(cli.server.received) == received
    assert "cases" not in outcome.summary


# A change of versions


def test_a_new_trialfolio_version_alone_is_a_revision_of_versions(
    cli: Cli, experiments: Builder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    earlier = tmp_path / "earlier"
    earlier.mkdir()
    fake_distribution(earlier, "trialfolio", "0.2.9")
    with monkeypatch.context() as patch:
        patch.syspath_prepend(earlier)
        out = completed(cli, experiments)
    installed = installed_versions().trialfolio
    received = len(cli.server.received)

    unrevised = experiments.run(EXAMPLE, out, approve=False)
    revised = experiments.run(EXAMPLE, out, "--revision-reason", "Upgraded Trial Folio.")

    assert unrevised.exit_code == 3
    assert unrevised.error["code"] == "plan.changed"
    assert revised.exit_code == 0, revised.stderr
    assert len(cli.server.received) == received
    # The entries before the last are the first plan's, unchanged, and the last has the reason
    # as given, and both versions (R03-AC03).
    second = record(out, 2)
    assert second.plans[:-1] == record(out, 1).plans
    assert second.plans[-1].reason == "Upgraded Trial Folio."
    changes = second.plans[-1].changes
    assert changes is not None
    assert changes.versions == (
        VersionChange(package="trialfolio", previous="0.2.9", current=installed),
    )
    assert (changes.parts, changes.cases_added, changes.cases_retired) == ((), (), ())


# The revision on a terminal


@posix_only
def test_on_a_terminal_the_revision_shows_what_changed_and_typing_approve_approves_it(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    old = next(case for case in record(out, 1).planned_cases if case.case_key == "holdings-50")
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", returns())
    reason = "Tries 40 holdings \x1b[2J instead."

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run",
            revision("holdings-40.yaml"),
            "--out",
            out,
            "--revision-reason",
            reason,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    new = next(case for case in record(out, 2).planned_cases if case.case_key == "holdings-50")
    assert "This plan revises the experiment's current plan, plan 1" in shown
    assert f"Cases added: holdings-50 ({new.case_id})" in shown
    assert f"Cases retired: holdings-50 ({old.case_id})" in shown
    assert "Reason for the revision: Tries 40 holdings \\u001b[2J instead." in shown
    assert "\x1b[2J" not in shown
    assert f"holdings-50 ({old.case_id}), last in plan 1: succeeded, after 1 attempt" in shown
    assert "Type approve to run this revision of the experiment's plan" in shown
    entry = record(out, 2).plans[-1]
    assert (entry.approval, entry.reason) == ("interactive", reason)
    assert session_manifest(out, 2, ExperimentManifest).approval == "interactive"


@posix_only
def test_on_a_terminal_a_refused_revision_fails_with_plan_changed(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    before = snapshot(out)

    with PseudoTerminal() as terminal:
        terminal.press("no\n")
        outcome = cli(
            "run",
            revision("holdings-40.yaml"),
            "--out",
            out,
            "--revision-reason",
            REASON,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    terminal.shown()

    assert outcome.exit_code == 3
    assert outcome.error["code"] == "plan.changed"
    assert "the answer wasn't approve" in outcome.error["message"]
    assert snapshot(out) == before


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("", id="empty"),
        pytest.param("  ", id="blank"),
        pytest.param("x" * 2001, id="long"),
    ],
)
def test_an_invalid_reason_is_a_usage_error_without_a_summary(cli: Cli, reason: str) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli("run", EXAMPLE, "--out", out, "--revision-reason", reason, "--json")

    assert outcome.exit_code == 2
    assert outcome.stdout == ""
    assert "argument --revision-reason" in outcome.stderr
    assert not out.exists()


@posix_only
def test_on_a_terminal_a_revision_without_a_reason_fails_without_asking(
    cli: Cli, experiments: Builder
) -> None:
    out = completed(cli, experiments)
    before = snapshot(out)

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run",
            revision("holdings-40.yaml"),
            "--out",
            out,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert outcome.exit_code == 3
    assert outcome.error["code"] == "plan.changed"
    assert "Reason for the revision: none given." in shown
    assert "Type approve" not in shown
    assert snapshot(out) == before
