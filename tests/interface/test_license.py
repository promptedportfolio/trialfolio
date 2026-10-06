"""The license acknowledgment: a data-processing command needs one, from the record, from
`TRIALFOLIO_ACCEPT_LICENSE`, or typed on a terminal; `--version`, `--help`, and `trialfolio license`
don't; and `trialfolio license` prints the license, the full notice, and the acknowledgment
status, or with `--accept` records the acknowledgment.

Traces to R01-AC20 (without an acknowledgment or a terminal, `run` fails with
`license.not_acknowledged` and exit 2, and writes nothing), and so does `review`, as release
0.2.0's failure behavior gives; R01-AC21 (`license --accept` writes exactly the four documented
fields, later runs don't ask, and another license identifier or notice version asks again); and
R01-AC22 (the exact `<license_id>/<notice_version>` acknowledges for the
process without a record, and any other value is rejected); and to docs/contracts.md, license
acknowledgment. Through the CLI's entry function in the test process, with the per-user
directories under a temporary home; the terminal is a real pseudo-terminal.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from tests.interface.conftest import Cli, config, snapshot
from tests.support.run_builder import REVIEW_CONFIGS
from tests.support.terminal import PseudoTerminal
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.notices import CONCISE_NOTICE, FULL_NOTICE, LICENSE_ID, NOTICE_VERSION
from trialfolio.userdirs import config_directory

REPO_ROOT = Path(__file__).resolve().parents[2]

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

RECORD_FIELDS = {"license_id", "notice_version", "acknowledged_at", "method"}

FIRST_READING = "2026-10-03T14:00:00Z"
"""The fixed clock's first time, as the record writes it."""


def record_path() -> Path:
    """The acknowledgment record, in the per-user configuration directory under the temporary
    home."""
    return config_directory(os.environ) / "acknowledgment.json"


def read_record() -> dict[str, object]:
    loaded: object = json.loads(record_path().read_bytes())
    assert isinstance(loaded, dict)
    return loaded  # pyright: ignore[reportUnknownVariableType]


def write_record(**changes: str) -> None:
    """Writes a record as `license --accept` would, with `changes` to its fields."""
    record = {
        "license_id": LICENSE_ID,
        "notice_version": NOTICE_VERSION,
        "acknowledged_at": "2026-10-01T09:00:00Z",
        "method": "command",
        **changes,
    }
    record_path().parent.mkdir(parents=True, exist_ok=True)
    record_path().write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def error_code(stdout: str) -> object:
    summary: object = json.loads(stdout)
    assert isinstance(summary, dict)
    error: object = summary["error"]  # pyright: ignore[reportUnknownVariableType]
    assert isinstance(error, dict)
    return error["code"]  # pyright: ignore[reportUnknownVariableType]


# R01-AC20: without an acknowledgment


@pytest.mark.parametrize("command", ["run", "demo", "report", "review"])
def test_without_an_acknowledgment_or_a_terminal_a_command_fails_and_writes_nothing(
    cli: Cli, command: str
) -> None:
    cli.credentials()
    out = cli.tmp / "out"
    first = {
        "run": ("run", config("formula.yaml")),
        "demo": ("demo",),
        "report": ("report", cli.tmp),
        "review": ("review", REVIEW_CONFIGS / "example.yaml"),
    }[command]

    outcome = cli(*first, "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome.stdout) == "license.not_acknowledged"
    assert "license.not_acknowledged" in outcome.stderr
    assert "trialfolio license --accept" in outcome.stderr
    assert f"{ACCEPT_VARIABLE}={ACCEPT_VALUE}" in outcome.stderr
    assert not out.exists()
    assert snapshot(cli.tmp) == {"home": None}
    assert cli.server.requests() == []


def test_version_and_help_work_without_an_acknowledgment(cli: Cli) -> None:
    version = cli("--version")
    helped = cli("--help")
    run_help = cli("run", "--help")

    assert (version.exit_code, version.stdout) == (0, "trialfolio 0.1.0\n")
    assert helped.exit_code == 0
    assert "run" in helped.stdout
    assert "license" in helped.stdout
    assert run_help.exit_code == 0
    assert "--approve" in run_help.stdout
    assert not record_path().exists()


def test_license_works_without_an_acknowledgment(cli: Cli) -> None:
    outcome = cli("license")

    assert outcome.exit_code == 0
    assert "Not acknowledged" in outcome.stdout
    assert not record_path().exists()


# R01-AC21: the record


def test_license_accept_writes_a_record_of_exactly_the_four_fields(cli: Cli) -> None:
    outcome = cli("license", "--accept")

    assert outcome.exit_code == 0, outcome.stderr
    record = read_record()
    assert set(record) == RECORD_FIELDS
    assert record == {
        "license_id": LICENSE_ID,
        "notice_version": NOTICE_VERSION,
        "acknowledged_at": FIRST_READING,
        "method": "command",
    }
    assert str(record_path()) in outcome.stdout
    assert record_path().is_relative_to(cli.home)


def test_after_license_accept_a_run_doesnt_ask_again(cli: Cli) -> None:
    assert cli("license", "--accept").exit_code == 0

    outcome = cli("demo", "--out", cli.tmp / "out")

    assert outcome.exit_code == 0, outcome.stderr
    assert "Type accept" not in outcome.stderr


@posix_only
def test_after_license_accept_a_run_on_a_terminal_shows_no_prompt(cli: Cli) -> None:
    assert cli("license", "--accept").exit_code == 0

    with PseudoTerminal() as terminal:
        outcome = cli(
            "demo", "--out", cli.tmp / "out", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    assert "Type accept" not in shown
    assert CONCISE_NOTICE not in shown


@pytest.mark.parametrize(
    "changes",
    [{"license_id": "LicenseRef-NSPRL-0.9"}, {"notice_version": "0.9"}],
    ids=["another-license-id", "another-notice-version"],
)
def test_a_record_of_another_license_or_notice_version_doesnt_acknowledge(
    cli: Cli, changes: dict[str, str]
) -> None:
    write_record(**changes)
    out = cli.tmp / "out"

    outcome = cli("demo", "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome.stdout) == "license.not_acknowledged"
    assert not out.exists()


@posix_only
@pytest.mark.parametrize(
    "changes",
    [{"license_id": "LicenseRef-NSPRL-0.9"}, {"notice_version": "0.9"}],
    ids=["another-license-id", "another-notice-version"],
)
def test_a_record_of_another_license_or_notice_version_brings_the_prompt_back(
    cli: Cli, changes: dict[str, str]
) -> None:
    write_record(**changes)

    with PseudoTerminal() as terminal:
        terminal.press("accept\n")
        outcome = cli(
            "demo", "--out", cli.tmp / "out", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    assert CONCISE_NOTICE in shown
    assert f"{LICENSE_ID}. Notice version {NOTICE_VERSION}." in shown
    assert "trialfolio license" in shown
    assert "Type accept to acknowledge them" in shown
    assert shown.index(CONCISE_NOTICE) < shown.index("Type accept")
    assert read_record() == {
        "license_id": LICENSE_ID,
        "notice_version": NOTICE_VERSION,
        "acknowledged_at": FIRST_READING,
        "method": "interactive",
    }


@posix_only
def test_typing_accept_on_a_terminal_records_an_interactive_acknowledgment(cli: Cli) -> None:
    with PseudoTerminal() as terminal:
        terminal.press("accept\n")
        outcome = cli(
            "demo", "--out", cli.tmp / "out", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    assert "Type accept" in shown
    record = read_record()
    assert set(record) == RECORD_FIELDS
    assert record["method"] == "interactive"
    assert (cli.tmp / "out" / "manifest.json").exists()


@posix_only
@pytest.mark.parametrize(
    "keys",
    ["no\n", "\n", "\x04", "Accept\n", " accept\n", "accept \n", "approve\n"],
    ids=[
        "another-word",
        "empty-line",
        "end-of-input",
        "capitalized",
        "leading",
        "trailing",
        "approve",
    ],
)
def test_any_other_answer_on_a_terminal_is_a_refusal_and_writes_nothing(
    cli: Cli, keys: str
) -> None:
    out = cli.tmp / "out"

    with PseudoTerminal() as terminal:
        terminal.press(keys)
        outcome = cli("demo", "--out", out, "--json", stdin=terminal.stdin, stderr=terminal.stderr)
    shown = terminal.shown()

    assert outcome.exit_code == 2
    assert error_code(outcome.stdout) == "license.not_acknowledged"
    assert "Type accept" in shown
    assert not record_path().exists()
    assert not out.exists()


@posix_only
def test_a_terminal_for_stderr_alone_isnt_asked(cli: Cli) -> None:
    out = cli.tmp / "out"

    with PseudoTerminal() as terminal:
        outcome = cli("demo", "--out", out, "--json", stderr=terminal.stderr)
    shown = terminal.shown()

    assert outcome.exit_code == 2
    assert error_code(outcome.stdout) == "license.not_acknowledged"
    assert "Type accept" not in shown
    assert not out.exists()


# R01-AC22: TRIALFOLIO_ACCEPT_LICENSE


def test_the_exact_value_acknowledges_for_the_process_without_a_record(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ACCEPT_VARIABLE, f"{LICENSE_ID}/{NOTICE_VERSION}")

    outcome = cli("demo", "--out", cli.tmp / "out")

    assert outcome.exit_code == 0, outcome.stderr
    assert not record_path().exists()
    assert not config_directory(os.environ).exists()


@pytest.mark.parametrize(
    "value",
    [
        LICENSE_ID,
        NOTICE_VERSION,
        "yes",
        ACCEPT_VALUE.lower(),
        ACCEPT_VALUE.upper(),
        f"{ACCEPT_VALUE} ",
    ],
    ids=[
        "license-id-alone",
        "notice-version-alone",
        "yes",
        "lowercase",
        "uppercase",
        "trailing-space",
    ],
)
def test_any_other_value_is_rejected(cli: Cli, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ACCEPT_VARIABLE, value)
    out = cli.tmp / "out"

    outcome = cli("demo", "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome.stdout) == "license.not_acknowledged"
    assert ACCEPT_VALUE in outcome.stderr
    assert not out.exists()
    assert not record_path().exists()


def test_another_value_is_rejected_even_with_a_record(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_record()
    monkeypatch.setenv(ACCEPT_VARIABLE, "yes")
    out = cli.tmp / "out"

    outcome = cli("demo", "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome.stdout) == "license.not_acknowledged"
    assert not out.exists()


# trialfolio license


def test_license_prints_the_license_the_full_notice_and_the_status(cli: Cli) -> None:
    outcome = cli("license")

    assert outcome.exit_code == 0
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.rstrip("\n") in outcome.stdout
    for paragraph in FULL_NOTICE:
        assert paragraph in outcome.stdout
    assert f"Acknowledgment of {LICENSE_ID}, notice version {NOTICE_VERSION}:" in outcome.stdout
    assert "Not acknowledged" in outcome.stdout
    assert "trialfolio license --accept" in outcome.stdout


def test_license_shows_a_recorded_acknowledgment(cli: Cli) -> None:
    assert cli("license", "--accept").exit_code == 0

    outcome = cli("license")

    assert outcome.exit_code == 0
    assert f"Acknowledged on {FIRST_READING} (command)" in outcome.stdout
    assert str(record_path()) in outcome.stdout


def test_license_shows_an_acknowledgment_for_the_process(cli: Cli) -> None:
    cli.accept_license()

    outcome = cli("license")

    assert outcome.exit_code == 0
    assert "Acknowledged for this process" in outcome.stdout
    assert not record_path().exists()


def test_license_accept_that_cant_be_written_fails(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = cli.tmp / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("TRIALFOLIO_CONFIG_DIR", str(blocker / "trialfolio"))

    outcome = cli("license", "--accept", "--json")

    assert outcome.exit_code == 4
    assert error_code(outcome.stdout) == "storage.write_failed"
    assert "TRIALFOLIO_ACCEPT_LICENSE" in outcome.stderr
    assert blocker.read_text(encoding="utf-8") == ""
