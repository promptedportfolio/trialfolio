"""`trialfolio run` rejects a misspelled or unsupported setting, or text sent without quotes, with
`config.invalid` before anything else: exit 3, no output directory, and no request, even with
credentials and an `--approve` given.

Traces to R01-AC02's interface part, through the CLI's entry function in the test process, over
the fake server. `tests/contract/test_screen_configuration.py` checks every invalid file at the
reader. A key the message names is escaped, so it can't act on the terminal, and the JSON summary
can hold the message (docs/contracts.md, configuration files; a corrected defect, 2026-10-10).
"""

from typing import cast

import pytest

from tests.interface.conftest import Cli, config, serve_success


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("invalid/misspelled-key.yaml", "max_holding"),
        ("invalid/slippage-five-decimals.yaml", "slippage_percent"),
        ("invalid/unquoted-rule.yaml", "rules[0]"),
    ],
)
def test_an_invalid_configuration_fails_before_anything_is_created_or_sent(
    cli: Cli, name: str, key: str
) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    outcome = cli("run", config(name), "--out", out, "--approve", "sha256:" + "a" * 64, "--json")

    assert outcome.exit_code == 3
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "config.invalid"
    assert key in error["message"]
    assert f"Error (config.invalid): {error['message']}" in outcome.stderr
    assert outcome.summary["output_dir"] is None
    assert outcome.summary["ids"] == {}
    assert not out.exists()
    assert cli.server.requests() == []


@pytest.mark.parametrize(
    ("keys", "shown"),
    [
        pytest.param('"\\u001b[2J": 1\n', "`\\u001b[2J` isn't a key", id="control-character"),
        pytest.param(
            '"\\ud800": 1\n"\\ud800": 2\n', "`\\ud800` appears more than once", id="lone-surrogate"
        ),
    ],
)
def test_a_key_in_an_error_message_cant_act_on_the_terminal(
    cli: Cli, keys: str, shown: str
) -> None:
    # A corrected defect: a message named a key as the file writes it, so an escape sequence
    # reached the terminal, and a lone surrogate made the message one the summary can't hold.
    cli.ready()
    path = cli.tmp / "keys.yaml"
    path.write_bytes(config("formula.yaml").read_bytes() + keys.encode())
    out = cli.tmp / "out"

    outcome = cli("run", path, "--out", out, "--approve", "sha256:" + "a" * 64, "--json")

    assert outcome.exit_code == 3
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "config.invalid"
    assert shown in error["message"]
    assert f"Error (config.invalid): {error['message']}" in outcome.stderr
    assert "\x1b" not in outcome.stderr
    assert not out.exists()
