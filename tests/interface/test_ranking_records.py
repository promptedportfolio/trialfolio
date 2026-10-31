"""A resume of an experiment with a ranking definition reads and checks its records before it
builds its plan, and refuses records with a ranking definition that are incomplete or changed
before it sends or writes anything; and a record 0.4.0 adds, of a schema version it has no reader
for, fails naming it.

Traces to R04-AC12 through the CLI, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_records.py`: one test for each break, each `input.not_a_run`, exit 3,
nothing sent, and no session reserved. Since TS-T06, the breaks of a copy of the committed
synthetic experiment, and the unbroken copy, are the cases of
tests/interface/test_experiment_records.py's two tests whose IDs name R04-AC12, beside R03-AC17's
(docs/test-refactoring.md, copies that check less, item 7). The breaks are an attempt with
`started.json` and no `updating.json`; an update record that disagrees with its start record; a
`started.json` whose exchanges don't end with `POST /rank` and its 200; a
`rank-update-request.json` whose bytes aren't what the attempt record records; an attempt record
1.1.0 under a plan 1.3.0; a `POST /screen/backtest` exchange that doesn't follow a `POST /rank`
with a 200; an attempt sent with a token after a 401 or a 403 to a `rank_update`; a plan whose
`definition.xml` is missing, or whose definition isn't `ranking_source`'s; and a weight row in
`settings.csv` that isn't its definition's. Each record 0.4.0 adds, with a schema version that has
no reader, fails with `artifact.unknown_schema_version`. Also to docs/contracts.md, running an
experiment (checking the records), sending a definition (resuming, in the core), and artifact
compatibility.

The CLI's entry function runs in the test process, with the real client, `requests`, and
`urllib3` over the fake server, and the ranking lock in the test's own directory. Each broken
experiment is run with `trialfolio run <config> --out <experiment> --approve <hash> --json`, with
the hash of the plan the experiment gave before it was broken, so only the records check can
refuse it. The broken experiments are copies of the committed
`experiments/synthetic-experiment-1.1.0/`, run with `ranking-synthetic-revised.yaml`, its current
plan, and, for the token a 401 or 403 to a `rank_update` dropped, an experiment the experiment
builder writes; `tests/support/broken_runs.py` breaks both, and updates the latest manifest's
entry for each file it edits, so each fails for the rule under test, which the message names.
`tests/core/test_ranking_resume.py` checks the same breaks at the core, and
`tests/interface/test_report_command.py` a run's, through `trialfolio report`.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.broken_runs import (
    UNKNOWN_RANKING_EXPERIMENT_SCHEMA_VERSIONS,
    attempt_id_of,
    attempt_of,
    copy_attempt,
    edit_record,
    unreadable,
)
from tests.support.cli import Cli
from tests.support.directories import snapshot
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    RANK_UPDATED,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns_each,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.synthetic_experiment import (
    RANKING_REVISED,
    SYNTHETIC_EXPERIMENT_WITH_DEFINITION,
)

type Builder = ExperimentBuilder[Outcome]

EXAMPLE = experiment_config("ranking-example.yaml")


def synthetic_copy(cli: Cli) -> tuple[Path, str]:
    """A copy of the committed synthetic experiment with a ranking definition, and the hash of
    the plan `trialfolio run` builds from `ranking-synthetic-revised.yaml` into it: its current
    plan's."""
    out = cli.tmp / "experiment"
    shutil.copytree(SYNTHETIC_EXPERIMENT_WITH_DEFINITION, out)
    return out, plan_hash(RANKING_REVISED, out)


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


# Copies of the synthetic experiment with a ranking definition, broken one way each


@pytest.mark.parametrize(
    ("target", "listed"),
    UNKNOWN_RANKING_EXPERIMENT_SCHEMA_VERSIONS.values(),
    ids=UNKNOWN_RANKING_EXPERIMENT_SCHEMA_VERSIONS.keys(),
)
def test_a_record_0_4_0_adds_whose_schema_version_has_no_reader_fails_naming_it(
    cli: Cli, target: Callable[[Path], str], listed: bool
) -> None:
    cli.ready()
    out, approve = synthetic_copy(cli)
    path = target(out)
    if listed:

        def newer(manifest: dict[str, list[dict[str, object]]]) -> None:
            (entry,) = (a for a in manifest["artifacts"] if a["path"] == path)
            unreadable(entry)

        edit_record(out, "sessions/2/manifest.json", newer)
    else:
        edit_record(out, path, unreadable)

    message = refused(cli, RANKING_REVISED, out, approve, "artifact.unknown_schema_version", 3)

    assert f"`{path}`" in message
    assert "9.9.9" not in message
    assert not (out / "sessions/3").exists()


# An experiment the builder writes, broken one way


@pytest.mark.parametrize("status", [401, 403])
def test_an_attempt_sent_with_a_token_a_401_or_403_to_a_rank_update_dropped_fails_the_check(
    cli: Cli, experiments: Builder, status: int
) -> None:
    # `value-heavy`'s rank_update gets the status, which drops the token the baseline's attempt
    # obtained, so `tilt-earnings-yield`'s attempt authenticates again, and `no-sales-yield`'s
    # sends with its token. A copy of `no-sales-yield`'s attempt, changed to name the baseline's
    # token, shows a case sent with a token the client no longer held.
    cli.ready()
    out = cli.tmp / "experiment"
    built = experiments.run(
        EXAMPLE,
        out,
        ranks=[RANK_UPDATED, Reply(status), RANK_UPDATED, RANK_UPDATED],
        sends=returns_each(3),
        authenticates=[AUTHENTICATED, AUTHENTICATED],
    )
    assert built.exit_code == 6, built.stderr
    assert cli.server.requests().count("POST /auth") == 2
    approve = plan_hash(EXAMPLE, out)
    removal = attempt_of(out, "no-sales-yield")
    tilt = attempt_id_of(attempt_of(out, "tilt-earnings-yield"))
    started = json.loads((out / removal / "started.json").read_bytes())
    assert started["authenticated_by"] == tilt
    baseline = attempt_id_of(attempt_of(out, "baseline"))
    copy = copy_attempt(out, removal, sequence=9, authenticated_by=baseline)

    message = refused(cli, EXAMPLE, out, approve, "input.not_a_run", 3)

    assert (
        f"the request of `{copy}/` was sent with a token that a 401 or 403 to an earlier"
        " request had dropped."
    ) in message
    assert not (out / "sessions/2").exists()
