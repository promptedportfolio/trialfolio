"""A resume reads and checks the experiment's records before it builds its plan, and refuses
records that are incomplete or changed, or that show a request sent again without a
confirmation, before it sends or writes anything. It refuses a record whose schema version it has
no reader for, a directory whose first plan was never recorded, and, once its records pass, a
synthetic experiment.

Traces to R03-AC17 (a resume whose records are incomplete or changed, or show a request sent again
without a confirmation, fails with `input.not_a_run` and exit 3, sends nothing, and reserves no
session; a record whose schema version has no reader fails with `artifact.unknown_schema_version`)
and to docs/contracts.md, running an experiment (a resumed experiment's step 4, and checking the
records), experiment attempts, an experiment's normalized tables (which parser wrote them),
`experiment.json`, the experiment manifest (a synthetic experiment stays synthetic), and artifact
compatibility. Through the CLI's entry function in the test process, with the real client,
`requests`, and `urllib3` over the fake server. Each broken experiment is run with
`trialfolio run <config> --out <experiment> --approve <hash> --json`, with the hash of the plan
the experiment gave before it was broken, so only the records check can refuse it.

The broken experiments are copies of the committed `experiments/synthetic-experiment-1.0.0/`,
run with `synthetic-revised.yaml`, its current plan, and experiments the experiment builder
writes, for the breaks that need a token dropped, a request sent again, or a table no manifest
lists; `tests/support/broken_runs.py` breaks both. A break that edits a record updates the latest
manifest's entry for it, and the `artifact_id` each `experiment.json` records for a plan's files,
so each fails for the rule under test, which the message names. tests/core/test_experiment_resume.py
checks the same breaks at the core.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.broken_runs import (
    BROKEN_EXPERIMENTS,
    UNKNOWN_EXPERIMENT_SCHEMA_VERSIONS,
    another_parser,
    attempt_id_of,
    attempt_of,
    attempts_of,
    case_of,
    edit_attempt,
    edit_record,
    unreadable,
)
from tests.support.cli import Cli
from tests.support.directories import snapshot
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    REFUSED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.storage_faults import FaultyStores
from tests.support.synthetic_experiment import FIRST, REVISED, SYNTHETIC_EXPERIMENT
from trialfolio.configuration import read_experiment_configuration
from trialfolio.planning import build_experiment_plan, installed_versions

type Builder = ExperimentBuilder[Outcome]

EXAMPLE = experiment_config("example.yaml")
DEFAULT_ONLY = experiment_config("default-only.yaml")


def synthetic_copy(cli: Cli) -> tuple[Path, str]:
    """A copy of the committed synthetic experiment, and the hash of the plan `trialfolio run`
    builds from `synthetic-revised.yaml` into it: its current plan's."""
    out = cli.tmp / "experiment"
    shutil.copytree(SYNTHETIC_EXPERIMENT, out)
    return out, plan_hash(REVISED, out)


def refused(cli: Cli, config: Path, out: Path, approve: str, code: str, exit_code: int) -> str:
    """Runs `config` into `out` with `--approve` and `approve`, checks that it fails with `code`
    and `exit_code`, on stderr and in the summary, and that it sent nothing and changed nothing in
    `out`, so it reserved no session, and gives the error's message."""
    before = snapshot(out)
    received = len(cli.server.received)

    outcome = cli("run", config, "--out", out, "--approve", approve, "--json")

    assert outcome.exit_code == exit_code, outcome.stderr
    error = outcome.error
    assert error["code"] == code
    assert f"Error ({code}): {error['message']}" in outcome.stderr
    assert len(cli.server.received) == received
    assert snapshot(out) == before
    return error["message"]


# Copies of the synthetic experiment, broken one way each


@pytest.mark.parametrize(
    ("breaking", "problem"), BROKEN_EXPERIMENTS.values(), ids=BROKEN_EXPERIMENTS.keys()
)
def test_a_broken_copy_of_the_synthetic_experiment_fails_the_records_check(
    cli: Cli, breaking: Callable[[Path], object], problem: str
) -> None:
    # The records are checked before the experiment is found synthetic, which run doesn't resume.
    cli.ready()
    out, approve = synthetic_copy(cli)
    breaking(out)

    message = refused(cli, REVISED, out, approve, "input.not_a_run", 3)

    assert problem in message
    assert "Another title" not in message
    assert not (out / "sessions/3").exists()


@pytest.mark.parametrize(
    "target",
    UNKNOWN_EXPERIMENT_SCHEMA_VERSIONS.values(),
    ids=UNKNOWN_EXPERIMENT_SCHEMA_VERSIONS.keys(),
)
def test_a_record_whose_schema_version_has_no_reader_fails_naming_it(
    cli: Cli, target: Callable[[Path], str]
) -> None:
    cli.ready()
    out, approve = synthetic_copy(cli)
    path = target(out)
    edit_record(out, path, unreadable)

    message = refused(cli, REVISED, out, approve, "artifact.unknown_schema_version", 3)

    assert message.startswith(
        f"Trial Folio can't read `{path}` in the output directory: it has a schema version this"
        " version has no reader for."
    )
    assert not (out / "sessions/3").exists()


def test_a_directory_whose_first_plan_wasnt_recorded_fails_and_says_to_remove_it(
    cli: Cli,
) -> None:
    # As a first run leaves it when it stops before its plan's experiment.json: the lock, the
    # session record, and the plan's other two files, and no manifest.
    cli.ready()
    out = cli.tmp / "experiment"
    for name in (
        "experiment.lock",
        "sessions/1/session.json",
        "plans/1/configuration.yaml",
        "plans/1/plan.json",
    ):
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SYNTHETIC_EXPERIMENT / name, out / name)
    configuration = read_experiment_configuration(FIRST.read_bytes(), str(FIRST))
    approve = build_experiment_plan(configuration, installed_versions()).plan_hash

    message = refused(cli, FIRST, out, approve, "output.not_empty", 4)

    assert "whose first run stopped before its first plan was recorded, so nothing was sent" in (
        message
    )
    assert "Remove the directory, and run the command again." in message


def test_an_unbroken_synthetic_experiment_passes_the_check_and_isnt_resumed(cli: Cli) -> None:
    cli.ready()
    out, approve = synthetic_copy(cli)

    message = refused(cli, REVISED, out, approve, "output.not_empty", 4)

    assert (
        "The output directory holds a synthetic experiment, whose values are invented, and"
        " trialfolio run doesn't resume one"
    ) in message
    assert "Run the configuration into another output directory." in message
    assert not (out / "sessions/3").exists()


# Experiments the builder writes, broken one way each


def test_a_latest_manifest_labeled_synthetic_though_the_plans_arent_fails_the_records_check(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(DEFAULT_ONLY, out, sends=[returns(), returns()]).exit_code == 0
    approve = plan_hash(DEFAULT_ONLY, out)
    edit_record(
        out,
        "sessions/1/manifest.json",
        lambda manifest: manifest.update(synthetic=True, approval="not_required", command=None),
    )

    message = refused(cli, DEFAULT_ONLY, out, approve, "input.not_a_run", 3)

    assert (
        "`sessions/1/manifest.json` is synthetic, though the experiment's plans don't record the"
        " approval not_required."
    ) in message
    assert not (out / "sessions/2").exists()


@pytest.mark.parametrize("status", [401, 403])
def test_a_request_sent_with_a_token_a_401_or_403_dropped_fails_the_records_check(
    cli: Cli, experiments: Builder, status: int
) -> None:
    # `liquidity-100m`'s request gets the status, which drops the token the baseline's attempt
    # obtained, so `holdings-50`'s attempt authenticates again, and the default variant's sends
    # with its token. The default variant's records, changed to name the baseline's token, show a
    # request sent with a token the client no longer held.
    cli.ready()
    out = cli.tmp / "experiment"
    built = experiments.run(
        EXAMPLE,
        out,
        sends=[returns(), Reply(status), returns(), returns(), returns()],
        authenticates=[AUTHENTICATED, AUTHENTICATED],
    )
    assert built.exit_code == 6, built.stderr
    approve = plan_hash(EXAMPLE, out)
    default = attempt_of(out, "rebalance-weeks-1")
    started = json.loads((out / default / "started.json").read_bytes())
    assert started["authenticated_by"] == attempt_id_of(attempt_of(out, "holdings-50"))
    baseline = attempt_id_of(attempt_of(out, "baseline"))
    edit_attempt(out, default, lambda record: record.update(authenticated_by=baseline))

    message = refused(cli, EXAMPLE, out, approve, "input.not_a_run", 3)

    assert (
        f"the request of `{default}/` was sent with a token that a 401 or 403 to an earlier"
        " request had dropped."
    ) in message
    assert not (out / "sessions/2").exists()


def test_an_attempt_sent_again_without_a_confirmed_repeat_fails_the_records_check(
    cli: Cli, experiments: Builder
) -> None:
    # `holdings-50`'s request gets a 503, so its attempt is unknown, possibly charged, and a
    # confirmed repeat sends it again. The repeat's records, changed to name no repeat, show a
    # request that may have been charged sent again without a confirmation.
    cli.ready()
    out = cli.tmp / "experiment"
    sends = [returns(), returns(), UNAVAILABLE, returns(), returns()]
    assert experiments.run(EXAMPLE, out, sends=sends).exit_code == 6
    unknown = attempt_id_of(attempt_of(out, "holdings-50"))
    repeat = f"holdings-50:{unknown}"
    assert experiments.run(EXAMPLE, out, "--repeat", repeat, sends=[returns()]).exit_code == 0
    approve = plan_hash(EXAMPLE, out)
    first, repeated = attempts_of(out, "holdings-50")
    assert attempt_id_of(first) == unknown
    edit_attempt(out, repeated, lambda record: record.update(repeat_of=None))

    message = refused(cli, EXAMPLE, out, approve, "input.not_a_run", 3)

    assert (
        f"`{repeated}/` was started after an attempt of its case whose request may have been"
        " charged, without a confirmed repeat of it."
    ) in message
    assert not (out / "sessions/3").exists()


def test_a_table_in_a_case_without_a_succeeded_attempt_fails_the_records_check(
    cli: Cli, experiments: Builder
) -> None:
    # `holdings-50`'s request gets a 503, so it has no succeeded attempt, and no tables. The
    # baseline's, copied into its directory, are tables none of its attempts could have written.
    cli.ready()
    out = cli.tmp / "experiment"
    sends = [returns(), returns(), UNAVAILABLE, returns(), returns()]
    assert experiments.run(EXAMPLE, out, sends=sends).exit_code == 6
    approve = plan_hash(EXAMPLE, out)
    holdings = case_of(out, "holdings-50")
    shutil.copytree(
        out / "cases" / case_of(out, "baseline") / "normalized",
        out / "cases" / holdings / "normalized",
    )

    message = refused(cli, EXAMPLE, out, approve, "input.not_a_run", 3)

    assert f"`cases/{holdings}/` has normalized tables, but no succeeded attempt." in message
    assert not (out / "sessions/2").exists()


def test_a_metrics_table_the_installed_parser_doesnt_write_says_to_resume_with_its_version(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    # The first session's authentication call gets a 401, and it ends with its manifest, having
    # sent nothing. The second sends the baseline, and an interrupt just after its metrics.csv
    # ends it without a manifest, so no manifest lists the table, or names the parser that wrote
    # it. Rewritten as another parser might write it, as after an upgrade whose parser reads the
    # response differently, it isn't what the installed parser writes.
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(DEFAULT_ONLY, out, authenticates=[REFUSED]).exit_code == 6
    baseline = case_of(out, "baseline")
    faults.fail_before(f"{baseline}/settings.csv", KeyboardInterrupt())
    stopped = experiments.run(DEFAULT_ONLY, out, sends=[returns(), returns()], store_factory=faults)
    assert stopped.exit_code == 130, stopped.stderr
    path = f"cases/{baseline}/normalized/metrics.csv"
    assert (out / path).is_file() and not (out / "sessions/2/manifest.json").exists()
    approve = plan_hash(DEFAULT_ONLY, out)
    another_parser(out, path)

    message = refused(cli, DEFAULT_ONLY, out, approve, "input.not_a_run", 3)

    assert (
        f"`{path}`, which no session's manifest lists, isn't what this version's parser writes"
        " from its response"
    ) in message
    # The version that wrote it is the one the session since the latest manifest records.
    version = json.loads((out / "sessions/2/session.json").read_bytes())["trialfolio_version"]
    assert (
        "Resume the experiment first with the version of Trial Folio that wrote it, one of those"
        f" the sessions since the latest manifest record ({version})"
    ) in message
    assert not (out / "sessions/3").exists()
