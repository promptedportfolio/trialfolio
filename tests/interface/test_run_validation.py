"""`trialfolio run` rejects a misspelled or unsupported setting, or a formula without quotes, with
`config.invalid` before anything else: exit 3, no output directory, and no request, even with
credentials and an `--approve` given.

Traces to R01-AC02's interface part, through the CLI's entry function in the test process, over
the fake server. `tests/contract/test_screen_configuration.py` checks every invalid file at the
reader.
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
