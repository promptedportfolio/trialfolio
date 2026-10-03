"""The plan hash `trialfolio run` shows depends only on the resolved settings, the title, and the
purpose: the same configuration gives the same hash in separate processes with different output
directories, and so do files that differ only in how they're written; changing a setting, the
title, or the purpose changes it. The request sends each number with the text `params` holds.

Traces to R01-AC25's interface part. The hashes come from `ids.plan_hash` in `run --json` without
approval, each run in its own process of the installed command: without approval nothing is sent,
so the test launcher isn't needed. The request's text is checked in the test process, through the
CLI's entry function, over the fake server.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, config, plan_hash_for, serve_success


def shown_hash(cli: Cli, path: Path, out: Path) -> str:
    """The plan hash `trialfolio run --json` gives without approval, in a new process."""
    result = subprocess.run(
        [sys.executable, "-m", "trialfolio", "run", str(path), "--out", str(out), "--json"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        cwd=cli.tmp,
        env=dict(os.environ),
    )
    assert result.returncode == 2, result.stderr
    summary = cast("dict[str, object]", json.loads(result.stdout))
    error = cast("dict[str, str]", summary["error"])
    assert error["code"] == "plan.approval_required"
    assert not out.exists()
    return cast("dict[str, str]", summary["ids"])["plan_hash"]


def changed(cli: Cli, old: str, new: str) -> Path:
    """`formula.yaml` with `old` replaced by `new`."""
    text = config("formula.yaml").read_text(encoding="utf-8")
    assert old in text
    path = cli.tmp / f"changed-{len(list(cli.tmp.glob('changed-*')))}.yaml"
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


def test_the_same_settings_give_the_same_hash_in_separate_processes(cli: Cli) -> None:
    cli.accept_license()

    hashes = {
        name: shown_hash(cli, config(name), cli.tmp / f"out-{index}" / "nested")
        for index, name in enumerate(
            ["formula.yaml", "written-differently.yaml", "vendor-factset.yaml"]
        )
    }

    assert len(set(hashes.values())) == 1
    assert hashes["formula.yaml"] == plan_hash_for(config("formula.yaml"))
    assert shown_hash(cli, config("formula.yaml"), cli.tmp / "elsewhere") == hashes["formula.yaml"]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("max_holdings: 25", "max_holdings: 50", id="a-setting"),
        pytest.param(
            "title: Earnings yield with a liquidity floor",
            "title: Earnings yield with a liquidity floor, again",
            id="the-title",
        ),
        pytest.param(
            "purpose: Reference backtest for the 0.1.0 response layout.",
            "purpose: Another purpose.",
            id="the-purpose",
        ),
    ],
)
def test_changing_a_setting_the_title_or_the_purpose_changes_the_hash(
    cli: Cli, old: str, new: str
) -> None:
    cli.accept_license()

    original = shown_hash(cli, config("formula.yaml"), cli.tmp / "out-original")
    other = shown_hash(cli, changed(cli, old, new), cli.tmp / "out-changed")

    assert other != original


def number_text(text: str, key: str) -> str:
    (found,) = re.findall(rf'"{key}": ([^,\s}}]+)', text)
    return found


@pytest.mark.parametrize(
    ("name", "expected"),
    [("slippage-whole.yaml", "1.0"), ("formula.yaml", "0.25")],
)
def test_the_request_sends_slippage_with_the_text_params_hold(
    cli: Cli, name: str, expected: str
) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    path = config(name)

    outcome = cli("run", path, "--out", out, "--approve", plan_hash_for(path), "--json")

    assert outcome.exit_code == 0, outcome.stderr
    body = cli.server.received[-1].body.decode("utf-8")
    assert number_text(body, "slippage") == expected
    assert type(json.loads(body)["slippage"]) is float
    (attempt,) = (out / "cases").glob("*/attempts/*")
    assert number_text((attempt / "request.json").read_text(encoding="utf-8"), "slippage") == (
        expected
    )
    assert number_text((out / "plan.json").read_text(encoding="utf-8"), "slippage") == expected
