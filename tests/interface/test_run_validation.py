"""`trialfolio run` rejects a misspelled or unsupported setting, or text sent without quotes, with
`config.invalid` before anything else: exit 3, no output directory, and no request, even with
credentials and an `--approve` given.

Traces to R01-AC02's interface part, through the CLI's entry function in the test process, over
the fake server; and to release 0.3.0's other checks in the default suite, which R03-T13 wrote
ahead of R03-T11: `run` chooses the experiment's reader by the configuration's `kind`, and an
invalid experiment configuration fails the same way, as does a `kind` `run` doesn't take. `tests/contract/test_screen_configuration.py` checks every invalid file at the
reader. A key the message names is escaped, so it can't act on the terminal, and the JSON summary
can hold the message (docs/contracts.md, configuration files; a corrected defect, 2026-10-10).

Also to R04-AC02's interface part, as release 0.4.0's test pairing gives it for
`tests/interface/test_run_validation.py`, which R04-T13 wrote: `not-well-formed.xml` and
`weight-zero.xml`, each named by a copy of `screen-configs/definition.yaml`, and the experiment
configurations `path-no-node.yaml`, `path-two-nodes.yaml`, `set-weight-zero.yaml`, and
`remove-only-factor.yaml`, each fail with `config.invalid`, exit 3, before anything is created
or sent, with a message that names the configuration's key and the rule, never the
definition's text or a path's. `tests/contract/test_ranking_definitions.py` checks every invalid
definition and ranking variant at the reader.
"""

import shutil
from typing import cast

import pytest

from tests.interface.conftest import Cli, config, serve_success
from tests.support.experiment_builder import RANK_UPDATED, experiment_config


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


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("invalid/misspelled-key.yaml", "`purpos`"),
        ("invalid/variant-universe.yaml", "`variants.universe`"),
        ("invalid/budget-below-cases.yaml", "`budget.provider_requests`"),
    ],
)
def test_an_invalid_experiment_configuration_fails_before_anything_is_created_or_sent(
    cli: Cli, name: str, key: str
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli(
        "run", experiment_config(name), "--out", out, "--approve", "sha256:" + "a" * 64, "--json"
    )

    assert outcome.exit_code == 3
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "config.invalid"
    assert key in error["message"]
    assert outcome.summary["ids"] == {}
    assert not out.exists()
    assert cli.server.requests() == []


@pytest.mark.parametrize(
    ("document", "problem"),
    [
        pytest.param(
            b"kind: review\n",
            "`kind` must be screen, experiment, or ranking-snapshot.",
            id="another-kind",
        ),
        pytest.param(
            b"title: No kind\n",
            "`kind` is required. A screen configuration has `kind: screen`, an experiment"
            " configuration has `kind: experiment`, and a ranking-snapshot configuration has"
            " `kind: ranking-snapshot`.",
            id="no-kind",
        ),
    ],
)
def test_run_takes_a_screen_an_experiment_or_a_snapshot_by_its_kind(
    cli: Cli, document: bytes, problem: str
) -> None:
    """From release 0.4.0's R04-T10, `run` takes a ranking snapshot configuration too, so the
    message names the three kinds, where 0.3.0's named two."""
    cli.ready()
    path = cli.tmp / "other.yaml"
    path.write_bytes(document)

    outcome = cli("run", path, "--out", cli.tmp / "out", "--json")

    assert outcome.exit_code == 3
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "config.invalid"
    assert problem in error["message"]


# A ranking definition (R04-AC02)

INVALID_DEFINITIONS = experiment_config("ranking/invalid")
DEFINITION_PATH = "'../experiment-configs/ranking/value-momentum.xml'"
"""How `screen-configs/definition.yaml` names its definition."""


def serve_ranking(cli: Cli) -> None:
    """Scripts the replies a run with a definition would get, so a request sent would be
    answered rather than refused."""
    serve_success(cli.server)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")


@pytest.mark.parametrize(
    ("name", "rule"),
    [
        ("not-well-formed.xml", "it isn't well-formed XML 1.0"),
        ("weight-zero.xml", "a node's Weight is 0"),
    ],
)
def test_an_invalid_definition_fails_before_anything_is_created_or_sent(
    cli: Cli, name: str, rule: str
) -> None:
    cli.ready()
    serve_ranking(cli)
    shutil.copyfile(INVALID_DEFINITIONS / name, cli.tmp / "ranking.xml")
    text = config("definition.yaml").read_text(encoding="utf-8")
    assert text.count(DEFINITION_PATH) == 1
    path = cli.tmp / "definition.yaml"
    path.write_text(text.replace(DEFINITION_PATH, "'ranking.xml'"), encoding="utf-8")
    out = cli.tmp / "out"

    outcome = cli("run", path, "--out", out, "--approve", "sha256:" + "a" * 64, "--json")

    assert outcome.exit_code == 3
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "config.invalid"
    assert "`ranking.definition`" in error["message"]
    assert rule in error["message"]
    # No text of the definition, such as a node's name or type.
    for text_of_it in ("Earnings Yield", "Composite", "StockFormula"):
        assert text_of_it not in error["message"]
    assert outcome.summary["output_dir"] is None
    assert not out.exists()
    assert cli.server.requests() == []


@pytest.mark.parametrize(
    ("name", "key", "path_text"),
    [
        ("path-no-node.yaml", "`variants.ranking[1].set[1]`", "Sales Yields"),
        ("path-two-nodes.yaml", "`variants.ranking[1].remove`", "Value P"),
        ("set-weight-zero.yaml", "`variants.ranking[0].set[1]`", "Momentum"),
        ("remove-only-factor.yaml", "`variants.ranking[1].remove`", "Book Yield"),
    ],
)
def test_an_invalid_ranking_variant_fails_before_anything_is_created_or_sent(
    cli: Cli, name: str, key: str, path_text: str
) -> None:
    cli.ready()
    serve_ranking(cli)
    out = cli.tmp / "experiment"

    outcome = cli(
        "run",
        experiment_config(f"invalid/{name}"),
        "--out",
        out,
        "--approve",
        "sha256:" + "a" * 64,
        "--json",
    )

    assert outcome.exit_code == 3
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "config.invalid"
    assert key in error["message"]
    # The entry is named by its place, never by its path's text, the user's strategy definition.
    assert path_text not in error["message"]
    assert outcome.summary["ids"] == {}
    assert not out.exists()
    assert cli.server.requests() == []
