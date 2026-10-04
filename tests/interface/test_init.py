"""`trialfolio init` sets up a workspace: a new or empty folder, the current one by default, with
the starter screen configuration, a README, and a `.gitignore`, and nothing else. It needs no
license acknowledgment, sends nothing, and logs to the per-user log directory.

Traces to R01-AC33 (release 0.1.0) and to docs/contracts.md, CLI behavior, and to R01-AC20's
commands that work without an acknowledgment. Through the CLI's entry function in the test
process, with the per-user directories under a temporary home.
"""

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, FaultyStores, snapshot
from tests.support.git import outside_any_repository
from trialfolio.configuration import read_screen_configuration
from trialfolio.planning import VERIFIED_VERSIONS, Versions, build_plan
from trialfolio.starter import starter_files
from trialfolio.userdirs import config_directory, log_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION = importlib.metadata.version("trialfolio")
STARTER = dict(starter_files(VERSION))


def error_of(outcome_stdout: str) -> dict[str, str]:
    summary = json.loads(outcome_stdout)
    return cast("dict[str, str]", summary["error"])


def test_init_writes_the_starter_files_and_nothing_else(cli: Cli) -> None:
    workspace = cli.tmp / "research" / "screens"

    outcome = cli("init", workspace)

    assert outcome.exit_code == 0, outcome.stderr
    assert snapshot(workspace) == STARTER
    assert set(STARTER) == {"screen.yaml", "README.md", ".gitignore"}
    assert outcome.stdout.splitlines() == [
        f"Set up a workspace in {workspace}: screen.yaml, README.md, and .gitignore.",
        (
            "Next, change screen.yaml. Then, from the workspace, review its plan with:"
            " trialfolio run screen.yaml --out runs/first/"
        ),
        "README.md lists the steps.",
    ]
    assert cli.server.requests() == []


def test_init_needs_no_acknowledgment_and_records_none(cli: Cli) -> None:
    outcome = cli("init", cli.tmp / "workspace")

    assert outcome.exit_code == 0, outcome.stderr
    assert not (config_directory(os.environ) / "acknowledgment.json").exists()


def test_init_logs_to_the_per_user_log_directory(cli: Cli) -> None:
    workspace = cli.tmp / "workspace"

    outcome = cli("init", workspace)

    assert outcome.exit_code == 0, outcome.stderr
    assert not (workspace / "logs").exists()
    log = log_directory(os.environ) / "trialfolio.log"
    assert "trialfolio init ended" in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("log_dir", [".", "logs", "nested/logs"])
def test_a_log_directory_in_the_workspace_gets_no_log(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, log_dir: str
) -> None:
    workspace = cli.tmp / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("TRIALFOLIO_LOG_DIR", log_dir)

    outcome = cli("init")

    assert outcome.exit_code == 0, outcome.stderr
    assert snapshot(workspace) == STARTER
    assert "The log directory is in the workspace" in outcome.stderr


def test_a_workspace_that_holds_the_default_log_directory_gets_no_log(cli: Cli) -> None:
    # The temporary home is empty, and each platform's default log directory is in it.
    outcome = cli("init", cli.home)

    assert outcome.exit_code == 0, outcome.stderr
    assert snapshot(cli.home) == STARTER


def test_a_log_directory_in_a_workspace_that_isnt_empty_leaves_it_unchanged(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = cli.tmp / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_bytes(b"mine")
    before = snapshot(workspace)
    # Through a symbolic link, so only the resolved path shows it's in the workspace.
    (cli.tmp / "link").symlink_to(workspace, target_is_directory=True)
    monkeypatch.setenv("TRIALFOLIO_LOG_DIR", str(cli.tmp / "link" / "logs"))

    outcome = cli("init", workspace, "--json")

    assert outcome.exit_code == 4
    assert error_of(outcome.stdout)["code"] == "output.not_empty"
    assert snapshot(workspace) == before


# The workspace's name, and another spelling of it: in another case, which macOS's and Windows'
# file systems ignore by default, and in another Unicode normalization, which macOS's ignores.
SPELLINGS = [("Workspace", "workspace"), ("Caf\u00e9", "Cafe\u0301")]


@pytest.mark.parametrize(("name", "spelling"), SPELLINGS)
def test_a_log_directory_in_another_spelling_of_a_new_workspace_gets_no_log(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, name: str, spelling: str
) -> None:
    workspace = cli.tmp / name
    monkeypatch.setenv("TRIALFOLIO_LOG_DIR", str(cli.tmp / spelling / "logs"))

    outcome = cli("init", workspace)

    assert outcome.exit_code == 0, outcome.stderr
    assert snapshot(workspace) == STARTER
    # Neither exists yet, so they're compared as a file system that ignores the difference would.
    assert "The log directory is in the workspace" in outcome.stderr


@pytest.mark.parametrize(("name", "spelling"), SPELLINGS)
def test_a_log_directory_in_another_spelling_of_an_occupied_workspace_leaves_it_unchanged(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, name: str, spelling: str
) -> None:
    workspace = cli.tmp / name
    workspace.mkdir()
    (workspace / "notes.txt").write_bytes(b"mine")
    before = snapshot(workspace)
    # On a file system that tells the spellings apart, the log goes to another folder.
    monkeypatch.setenv("TRIALFOLIO_LOG_DIR", str(cli.tmp / spelling / "logs"))

    outcome = cli("init", workspace, "--json")

    assert outcome.exit_code == 4
    assert error_of(outcome.stdout)["code"] == "output.not_empty"
    assert snapshot(workspace) == before


def test_init_without_a_directory_sets_up_the_current_one(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = cli.tmp / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    outcome = cli("init", "--json")

    assert outcome.exit_code == 0, outcome.stderr
    assert snapshot(workspace) == STARTER
    assert outcome.summary["output_dir"] == "."
    assert outcome.summary["outputs"] == {"configuration": "screen.yaml"}


def test_the_readme_links_to_this_versions_user_guide() -> None:
    readme = STARTER["README.md"].decode()

    assert (
        f"https://github.com/promptedportfolio/trialfolio/blob/v{VERSION}/docs/user-guide.md"
        in readme
    )
    assert "{version}" not in readme


def test_the_starter_configuration_has_a_comment_on_each_key() -> None:
    text = STARTER["screen.yaml"].decode()
    # Each key, `purpose` commented out included, and the comment after its value.
    comments = {
        match["key"]: match["comment"]
        for match in re.finditer(
            r"^ *(?:# )?(?P<key>[a-z_]+):[^#\n]*(?P<comment>#.*)?$", text, re.MULTILINE
        )
    }

    assert set(comments) == {
        "kind",
        "schema_version",
        "title",
        "purpose",
        "universe",
        "rules",
        "ranking",
        "formula",
        "lower_is_better",
        "max_holdings",
        "benchmark",
        "start_date",
        "end_date",
        "rebalance_weeks",
        "transaction_price",
        "slippage_percent",
        "pit_method",
        "precision",
    }
    assert [key for key, comment in comments.items() if not comment] == []
    assert "Write the text Portfolio123 receives in single quotes" in text


def test_the_starter_configuration_resolves_to_the_request_portfolio123_accepted() -> None:
    configuration = read_screen_configuration(STARTER["screen.yaml"], "screen.yaml")
    versions = Versions(
        trialfolio=VERSION,
        p123api=VERIFIED_VERSIONS["p123api"][0],
        requests=VERIFIED_VERSIONS["requests"][0],
        urllib3=VERIFIED_VERSIONS["urllib3"][0],
    )
    reference = REPO_ROOT / "reference" / "p123api-screen-backtest" / "request.json"

    (request,) = build_plan(configuration, versions).cases[0].requests

    assert configuration.purpose is None
    # Compared as JSON text, so a float and an integer can't pass for each other.
    assert json.dumps(request.params.model_dump(mode="json"), sort_keys=True) == json.dumps(
        json.loads(reference.read_text(encoding="utf-8")), sort_keys=True
    )


def test_from_the_workspace_run_shows_the_starter_plan_and_sends_nothing(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = cli.tmp / "workspace"
    assert cli("init", workspace).exit_code == 0
    monkeypatch.chdir(workspace)
    cli.accept_license()

    outcome = cli("run", "screen.yaml", "--out", "runs/first/", "--json")

    assert outcome.exit_code == 2
    assert error_of(outcome.stdout)["code"] == "plan.approval_required"
    assert not (workspace / "runs").exists()
    assert cli.server.requests() == []


@pytest.mark.skipif(shutil.which("git") is None, reason="needs Git")
def test_the_gitignore_keeps_credential_files_runs_and_reports_out_of_git(cli: Cli) -> None:
    workspace = cli.tmp / "workspace"
    assert cli("init", workspace).exit_code == 0
    git = ["git", "-C", str(workspace)]
    env = outside_any_repository()
    subprocess.run([*git, "init", "--quiet"], env=env, check=True, capture_output=True)

    def ignored(*paths: str) -> set[str]:
        result = subprocess.run(
            [*git, "check-ignore", *paths], env=env, capture_output=True, text=True, check=False
        )
        return set(result.stdout.splitlines())

    kept_out = {".env", ".env.local", "p123.env", "runs/first/report.html", "reports/first/x"}
    kept = {"screen.yaml", "README.md", ".gitignore", "notes/runs.md", "demo/report.html"}
    assert ignored(*kept_out, *kept) == kept_out


@pytest.mark.parametrize(
    "contents",
    [{"notes.txt": b"mine"}, {".DS_Store": b""}],
    ids=["a-file", "a-hidden-file"],
)
def test_a_directory_that_isnt_empty_is_left_as_it_is(cli: Cli, contents: dict[str, bytes]) -> None:
    workspace = cli.tmp / "workspace"
    workspace.mkdir()
    for name, data in contents.items():
        (workspace / name).write_bytes(data)
    before = snapshot(workspace)

    outcome = cli("init", workspace, "--json")

    assert outcome.exit_code == 4
    assert error_of(outcome.stdout)["code"] == "output.not_empty"
    assert outcome.summary["output_dir"] is None
    assert snapshot(workspace) == before


def test_a_blank_directory_is_a_usage_error(cli: Cli) -> None:
    outcome = cli("init", " ", "--json")

    assert outcome.exit_code == 2
    assert outcome.stdout == ""
    assert "it's blank" in outcome.stderr


def test_a_failed_write_says_nothing_was_sent_and_what_is_left(
    cli: Cli, faults: FaultyStores
) -> None:
    workspace = cli.tmp / "workspace"
    faults.fail_os("README.md")

    outcome = cli("init", workspace, "--json", store_factory=faults)

    assert outcome.exit_code == 4
    error = error_of(outcome.stdout)
    assert error["code"] == "storage.write_failed"
    assert error["message"].endswith(
        f" Nothing was sent. {workspace} holds some of the starter files: remove them, then run"
        " trialfolio init there again."
    )
    assert outcome.summary["output_dir"] == str(workspace)
    assert set(snapshot(workspace)) == {"screen.yaml"}


def test_an_interrupt_after_the_claim_says_nothing_was_sent_and_what_is_left(
    cli: Cli, faults: FaultyStores
) -> None:
    workspace = cli.tmp / "workspace"
    faults.fail_before(".gitignore", KeyboardInterrupt())

    outcome = cli("init", workspace, "--json", store_factory=faults)

    assert outcome.exit_code == 130
    error = error_of(outcome.stdout)
    assert error["code"] == "command.interrupted"
    assert error["message"].startswith("Trial Folio was interrupted. Nothing was sent.")
    assert "holds some of the starter files" in error["message"]
    assert set(snapshot(workspace)) == {"screen.yaml", "README.md"}
