"""The reference pages' generated regions match their sources, and the check fails when they don't.

Traces to docs/user-manual.md: UM-AC08, the generated reference pages match the CLI's help, the
committed schemas, and contracts.md's errors, and scripts/check fails when they don't; rule 2, the
reference pages that list commands, fields, and errors are generated; and UM-T02, a hand-written
column kept by each row's key, and the error codes cross-checked with `EXIT_CODES`. Most tests
write a small manual by hand, with regions the test registers, and run `scripts/manual_reference.py`
on it. The last ones run it on the real pages and sources, as scripts/check does, and check that
each JSON file the page of output fields names is at the version Trial Folio writes.
"""

import fnmatch
import importlib.util
import io
import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.support.clock import FixedClock
from tests.support.environment import VARIABLES
from tests.support.synthetic_experiment import write_synthetic_experiment
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import main as trialfolio
from trialfolio.contracts.schema_files import SCHEMA_FILES
from trialfolio.errors import EXIT_CODES

ROOT = Path(__file__).resolve().parents[2]


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "manual_reference", ROOT / "scripts" / "manual_reference.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["manual_reference"] = module
    spec.loader.exec_module(module)
    return module


manual_reference = _load_generator()
Region = manual_reference.Region
Table = manual_reference.Table


def _keys(*rows: tuple[str, ...], hand_written: bool = True) -> Any:
    """A region of one table, whose last column is hand-written unless `hand_written` is false."""
    header = ("Key", "Value", "Note") if hand_written else ("Key", "Value")
    return Region((Table(header, rows, hand_written=hand_written),))


REGISTERED = {
    "keys": _keys(("`a`", "One"), ("`b`", "Two")),
    "usage": Region(("```text\nprog [-h]\n```", Table(("Option", "What"), (("`-h`", "Help"),)))),
}
KEYS = """<!-- generated: keys -->

| Key | Value | Note |
|---|---|---|
| `a` | One | Written by hand |
| `b` | Two | Also by hand |

<!-- end generated: keys -->"""
USAGE = """<!-- generated: usage -->

```text
prog [-h]
```

| Option | What |
|---|---|
| `-h` | Help |

<!-- end generated: usage -->"""


def _manual(tmp_path: Path, **pages: str) -> Path:
    """A manual whose pages are `pages`, by name, with `__` for `/`."""
    manual = tmp_path / "manual"
    for name, text in pages.items():
        path = manual / (name.replace("__", "/") + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return manual


def _valid(tmp_path: Path) -> Path:
    return _manual(
        tmp_path,
        index=f"# Home\n\nHand-written.\n\n{KEYS}\n\nMore by hand.\n",
        reference__cli=f"# Commands\n\n{USAGE}\n",
    )


def _read(manual: Path, name: str) -> str:
    return (manual / name).read_text(encoding="utf-8")


# The check


def test_pages_that_match_their_regions_pass(tmp_path: Path) -> None:
    manual = _valid(tmp_path)

    assert manual_reference.check(manual, REGISTERED) == []


def test_a_generated_cell_edited_by_hand_fails(tmp_path: Path) -> None:
    manual = _valid(tmp_path)
    page = manual / "index.md"
    page.write_text(_read(manual, "index.md").replace("| One |", "| Uno |"), encoding="utf-8")

    assert manual_reference.check(manual, REGISTERED) == [
        "manual/index.md:5: region keys differs from what its source generates"
    ]


def test_a_hand_written_cell_edited_by_hand_passes(tmp_path: Path) -> None:
    manual = _valid(tmp_path)
    page = manual / "index.md"
    page.write_text(
        _read(manual, "index.md").replace("Also by hand", "Rewritten"), encoding="utf-8"
    )

    assert manual_reference.check(manual, REGISTERED) == []


def test_a_region_whose_source_changed_fails(tmp_path: Path) -> None:
    manual = _valid(tmp_path)
    changed = {**REGISTERED, "usage": Region(("```text\nprog [-h] [--json]\n```",))}

    assert manual_reference.check(manual, changed) == [
        "manual/reference/cli.md:3: region usage differs from what its source generates"
    ]


def test_an_unknown_region_fails(tmp_path: Path) -> None:
    unknown = "<!-- generated: gone -->\n\nOld.\n\n<!-- end generated: gone -->"
    manual = _valid(tmp_path)
    (manual / "extra.md").write_text(f"# Extra\n\n{unknown}\n", encoding="utf-8")

    assert manual_reference.check(manual, REGISTERED) == [
        "manual/extra.md:3: names region gone, which isn't registered"
    ]


def test_a_registered_region_on_no_page_fails(tmp_path: Path) -> None:
    manual = _manual(tmp_path, index=f"# Home\n\n{KEYS}\n")

    assert manual_reference.check(manual, REGISTERED) == [
        "region usage appears on no page in manual/"
    ]


def test_a_region_on_two_pages_fails(tmp_path: Path) -> None:
    manual = _valid(tmp_path)
    (manual / "again.md").write_text(f"# Again\n\n{USAGE}\n", encoding="utf-8")

    assert manual_reference.check(manual, REGISTERED) == [
        "region usage appears more than once: manual/again.md:3, manual/reference/cli.md:3"
    ]


def test_a_region_twice_on_one_page_fails(tmp_path: Path) -> None:
    manual = _manual(tmp_path, index=f"# Home\n\n{KEYS}\n\n{USAGE}\n\n{USAGE}\n")

    assert manual_reference.check(manual, REGISTERED) == [
        "region usage appears more than once: manual/index.md:12, manual/index.md:24"
    ]


@pytest.mark.parametrize(
    ("page", "problem"),
    [
        pytest.param(
            f"{KEYS}\n\n<!-- generated: usage -->\n\nNo end.\n",
            "manual/index.md:10: region usage starts, and never ends",
            id="a start without an end",
        ),
        pytest.param(
            f"{KEYS}\n\n<!-- end generated: usage -->\n",
            "manual/index.md:10: region usage ends, but no region started",
            id="an end without a start",
        ),
        pytest.param(
            KEYS.replace("<!-- end generated: keys -->", "<!-- end generated: usage -->"),
            "manual/index.md:8: region usage ends, but region keys started at line 1",
            id="an end of another region",
        ),
        pytest.param(
            KEYS.replace("| `b` |", "<!-- generated: usage -->\n| `b` |"),
            "manual/index.md:6: region usage starts inside region keys, which starts at line 1",
            id="a region inside another",
        ),
        pytest.param(
            KEYS.replace("<!-- end generated: keys -->", "<!--end generated: keys-->"),
            "manual/index.md:8: a marker that isn't one: <!--end generated: keys-->",
            id="a marker without its spaces",
        ),
    ],
)
def test_unbalanced_or_nested_markers_fail(tmp_path: Path, page: str, problem: str) -> None:
    manual = _manual(tmp_path, index=page, reference__cli=USAGE)

    assert problem in manual_reference.check(manual, REGISTERED)


# The hand-written column


def test_regenerating_keeps_each_hand_written_cell_by_its_key(tmp_path: Path) -> None:
    manual = _valid(tmp_path)
    # The source reorders the rows, changes a value, drops `b`, and adds `c`.
    source = {**REGISTERED, "keys": _keys(("`c`", "Three"), ("`a`", "Uno"))}

    problems = manual_reference.rewrite(manual, source)

    assert problems == ["manual/index.md: region keys: the row `c` has no 'Note' yet; write it"]
    assert "| `c` | Three | |\n| `a` | Uno | Written by hand |\n" in _read(manual, "index.md")
    assert "`b`" not in _read(manual, "index.md")
    assert _read(manual, "index.md").startswith("# Home\n\nHand-written.\n\n")
    assert _read(manual, "index.md").endswith("<!-- end generated: keys -->\n\nMore by hand.\n")


def test_an_empty_hand_written_cell_fails_the_check(tmp_path: Path) -> None:
    manual = _manual(
        tmp_path,
        index=KEYS.replace(" Also by hand ", " ") + "\n",
        reference__cli=USAGE,
    )

    assert manual_reference.check(manual, REGISTERED) == [
        "manual/index.md: region keys: the row `b` has no 'Note' yet; write it"
    ]


def test_regenerating_twice_changes_nothing_the_second_time(tmp_path: Path) -> None:
    manual = _manual(
        tmp_path,
        index="# Home\n\n<!-- generated: keys -->\n<!-- end generated: keys -->\n",
        reference__cli="<!-- generated: usage -->\nStale.\n<!-- end generated: usage -->",
    )

    manual_reference.rewrite(manual, REGISTERED)
    first = {path: path.read_bytes() for path in manual.rglob("*.md")}
    manual_reference.rewrite(manual, REGISTERED)

    assert {path: path.read_bytes() for path in manual.rglob("*.md")} == first
    assert _read(manual, "reference/cli.md") == USAGE


def test_a_marker_problem_leaves_every_page_as_it_is(tmp_path: Path) -> None:
    manual = _manual(
        tmp_path,
        index=KEYS.replace("| One |", "| Stale |") + "\n",
        reference__cli="<!-- generated: usage -->\n",
    )
    before = {path: path.read_bytes() for path in manual.rglob("*.md")}

    problems = manual_reference.rewrite(manual, REGISTERED)

    assert problems == [
        "manual/reference/cli.md:1: region usage starts, and never ends",
        "region usage appears on no page in manual/",
    ]
    assert {path: path.read_bytes() for path in manual.rglob("*.md")} == before


# contracts.md's errors

CONTRACTS = """# Contracts

## CLI behavior

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Completed |
| 3 | Invalid input |
| 4 | Output problem |

### JSON summary

| Code | Meaning |
|---|---|
| 9 | A table in another section |

## Errors

| Code | Exit | Meaning |
|---|---|---|
| `config.invalid` | 3 | See [the configuration](#screen-configuration), [D-01](spec.md#decisions), [a release](releases/0.1.0-api-execution.md#required-outputs), [the README](../README.md), and [elsewhere](https://example.com/a) |
| `output.not_empty` | 4 | Not empty |

## Interface-independent core
"""
CODES = {"config.invalid": 3, "output.not_empty": 4}


def test_the_errors_meanings_link_to_the_specification_on_github() -> None:
    regions = manual_reference.error_regions(CONTRACTS, CODES)

    text = manual_reference.render(regions["errors-codes"])
    blob = "https://github.com/promptedportfolio/trialfolio/blob/main/"
    assert (
        f"See [the configuration]({blob}docs/contracts.md#screen-configuration),"
        f" [D-01]({blob}docs/spec.md#decisions),"
        f" [a release]({blob}docs/releases/0.1.0-api-execution.md#required-outputs),"
        f" [the README]({blob}README.md), and [elsewhere](https://example.com/a)"
    ) in text
    assert "| `output.not_empty` | 4 | Not empty | |" in text
    assert manual_reference.render(regions["errors-exit-codes"]) == (
        "\n| Code | Meaning |\n|---|---|\n| 0 | Completed |\n| 3 | Invalid input |\n"
        "| 4 | Output problem |\n"
    )


def test_every_link_in_the_real_errors_leads_to_github() -> None:
    regions = manual_reference.error_regions(
        manual_reference.CONTRACTS.read_text(encoding="utf-8"), EXIT_CODES
    )

    targets = [
        part.split(")")[0]
        for region in regions.values()
        for part in manual_reference.render(region).split("](")[1:]
    ]
    assert targets
    assert all(target.startswith("https://github.com/") for target in targets)


@pytest.mark.parametrize(
    ("contracts", "codes", "problem"),
    [
        pytest.param(
            CONTRACTS.replace("| `output.not_empty` | 4 | Not empty |\n", ""),
            CODES,
            "EXIT_CODES has output.not_empty, which contracts.md's errors table lacks",
            id="a code only in EXIT_CODES",
        ),
        pytest.param(
            CONTRACTS,
            {"config.invalid": 3},
            "contracts.md's errors table has output.not_empty, which EXIT_CODES lacks",
            id="a code only in contracts.md",
        ),
        pytest.param(
            CONTRACTS,
            {"config.invalid": 3, "output.not_empty": 3},
            "output.not_empty exits 4 in contracts.md's errors table, and 3 in EXIT_CODES",
            id="another exit code",
        ),
        pytest.param(
            CONTRACTS.replace("| 4 | Output problem |\n", ""),
            CODES,
            "contracts.md's exit-code table lacks 4",
            id="an exit code the exit-code table lacks",
        ),
        pytest.param(
            CONTRACTS.replace("| 4 | Output problem |\n", "| 4 | Output problem |\n| 7 | New |\n"),
            CODES,
            "contracts.md's exit-code table has 7, which no error has",
            id="an exit code no error has",
        ),
    ],
)
def test_errors_that_disagree_with_exit_codes_fail(
    contracts: str, codes: Mapping[str, int], problem: str
) -> None:
    with pytest.raises(manual_reference.GenerationError) as raised:
        manual_reference.error_regions(contracts, codes)

    assert problem in str(raised.value)


def test_the_real_errors_table_missing_a_code_fails() -> None:
    contracts = manual_reference.CONTRACTS.read_text(encoding="utf-8")
    row = next(line for line in contracts.split("\n") if line.startswith("| `experiment.locked`"))

    with pytest.raises(manual_reference.GenerationError) as raised:
        manual_reference.error_regions(contracts.replace(row + "\n", ""), EXIT_CODES)

    assert "EXIT_CODES has experiment.locked, which contracts.md's errors table lacks" in str(
        raised.value
    )


# The schemas and the parser


def _schemas(tmp_path: Path, name: str, change: Any) -> Path:
    """A copy of schemas/, with `change` applied to the schema `name`."""
    schemas = tmp_path / "schemas"
    shutil.copytree(manual_reference.SCHEMAS, schemas)
    schema = json.loads((schemas / name).read_text(encoding="utf-8"))
    change(schema)
    (schemas / name).write_text(json.dumps(schema), encoding="utf-8")
    return schemas


SCREEN = "screen-configuration-1.0.0.schema.json"
RUN_MANIFEST = "run-manifest-1.0.0.schema.json"


def _options(schema: Any) -> Any:
    """The run manifest's `command.options`: a mapping of names to values."""
    return schema["$defs"]["CommandRecord"]["properties"]["options"]


@pytest.mark.parametrize(
    ("name", "change", "problem"),
    [
        pytest.param(
            SCREEN,
            lambda schema: schema["properties"]["rules"].update(uniqueItems=True),
            "rules uses uniqueItems, which the generator can't put in plain words",
            id="a keyword",
        ),
        pytest.param(
            SCREEN,
            lambda schema: schema["properties"]["universe"].update(pattern="^[A-Z]+$"),
            "universe has the pattern '^[A-Z]+$', which the generator can't put in plain words",
            id="a pattern",
        ),
        pytest.param(
            SCREEN,
            lambda schema: schema["properties"]["start_date"].update(format="time"),
            "start_date has the format time",
            id="a format",
        ),
        pytest.param(
            RUN_MANIFEST,
            lambda schema: next(iter(_options(schema)["patternProperties"].values()))["anyOf"][
                0
            ].update(allOf=[{"minLength": 1}]),
            "command.options.* uses allOf, which the generator can't put in plain words",
            id="a keyword in a mapping's values",
        ),
        pytest.param(
            RUN_MANIFEST,
            lambda schema: _options(schema)["propertyNames"].update(enum=["out"]),
            "command.options's keys use enum, which the generator can't put in plain words",
            id="a keyword in a mapping's keys",
        ),
        pytest.param(
            SCREEN,
            lambda schema: schema["properties"].update(
                universe={"type": "object", "additionalProperties": {"type": "number"}}
            ),
            "universe allows any key",
            id="an object of any keys, each a number",
        ),
        pytest.param(
            SCREEN,
            lambda schema: schema["properties"].update(
                universe={"type": "object", "additionalProperties": True}
            ),
            "universe allows any key",
            id="an object of any keys and values",
        ),
        pytest.param(
            SCREEN,
            lambda schema: schema["$defs"]["NameRanking"].pop("additionalProperties"),
            "ranking-name allows any key",
            id="an object that doesn't say it's closed",
        ),
        pytest.param(
            SCREEN,
            lambda schema: schema.pop("additionalProperties"),
            "the top level allows any key",
            id="a top level that doesn't say it's closed",
        ),
    ],
)
def test_a_schema_the_generator_cant_put_in_plain_words_fails(
    tmp_path: Path, name: str, change: Any, problem: str
) -> None:
    sources = manual_reference.default_sources()
    schemas = _schemas(tmp_path, name, change)

    with pytest.raises(manual_reference.GenerationError) as raised:
        manual_reference.generate(
            manual_reference.Sources(sources.parser, schemas, sources.contracts, EXIT_CODES)
        )

    assert str(raised.value) == f"{name}: {problem}"


def test_the_commands_dont_depend_on_the_terminal_or_the_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = manual_reference.cli_regions(manual_reference.default_sources().parser)
    monkeypatch.setenv("COLUMNS", "30")
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("LANGUAGE", "de")

    regions = manual_reference.cli_regions(manual_reference.default_sources().parser)

    assert regions == plain
    assert (
        "trialfolio run [-h] --out DIR [--approve PLAN_HASH]\n               [--revision-reason TEXT]\n"
    ) in manual_reference.render(regions["cli-command-run"])
    assert "| `-h`, `--help` | No | None | Show this help message and exit |" in (
        manual_reference.render(regions["cli-common-options"])
    )


def test_each_usage_line_is_wrapped_as_an_80_column_terminal_wraps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regions = manual_reference.cli_regions(manual_reference.default_sources().parser)
    commands = {
        region_id: [region_id.removeprefix("cli-command-"), "--help"]
        for region_id in regions
        if region_id.startswith("cli-command-")
    }
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("LANGUAGE", "C")
    monkeypatch.setenv("NO_COLOR", "1")
    for name in ("FORCE_COLOR", "PYTHON_COLORS"):
        monkeypatch.delenv(name, raising=False)

    assert commands
    for region_id, argv in {"cli-usage": ["--help"], **commands}.items():
        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)
        assert trialfolio(argv) == 0
        # The help starts with the usage, then a blank line. The page leaves out `usage: `, and
        # the seven columns it takes from each line.
        first, *rest = stdout.getvalue().split("\n\n")[0].split("\n")
        assert first.startswith("usage: ")
        assert all(line.startswith(" " * 7) for line in rest)
        shown = "\n".join([first.removeprefix("usage: "), *(line[7:] for line in rest)])
        assert f"```text\n{shown}\n```" in manual_reference.render(regions[region_id]), region_id


# The real pages


def test_the_committed_pages_match_their_sources(capsys: pytest.CaptureFixture[str]) -> None:
    generated = manual_reference.generate(manual_reference.default_sources())

    assert manual_reference.check(manual_reference.MANUAL, generated) == []
    assert manual_reference.main(["--check"]) == 0
    assert "match their sources" in capsys.readouterr().out


def test_regenerating_the_committed_pages_changes_nothing(tmp_path: Path) -> None:
    manual = tmp_path / "manual"
    shutil.copytree(manual_reference.MANUAL, manual)
    before = {path: path.read_bytes() for path in manual.rglob("*.md")}

    problems = manual_reference.rewrite(
        manual, manual_reference.generate(manual_reference.default_sources())
    )

    assert problems == []
    assert {path: path.read_bytes() for path in manual.rglob("*.md")} == before


# Where each JSON file a command writes is, by the region of output-fields.md that lists its fields.
RUN_FILES = {
    "manifest.json": "output-fields-run-manifest",
    "plan.json": "output-fields-run-plan",
    "cases/*/attempts/*/started.json": "output-fields-run-start-record",
    "cases/*/attempts/*/attempt.json": "output-fields-run-attempt-record",
}
EXPERIMENT_FILES = {
    "plans/*/plan.json": "output-fields-experiment-plan",
    "plans/*/experiment.json": "output-fields-experiment-record",
    "sessions/*/session.json": "output-fields-session-record",
    "sessions/*/manifest.json": "output-fields-session-manifest",
    "cases/*/attempts/*/started.json": "output-fields-experiment-start-record",
    "cases/*/attempts/*/attempt.json": "output-fields-experiment-attempt-record",
    "cases/*/attempts/*/authenticating.json": "output-fields-authentication-record",
}
REVIEW_FILES = {"manifest.json": "output-fields-review-manifest"}
# The files that have no schema: the request without credentials, and Portfolio123's response.
UNSCHEMED = {"request.json", "response.json"}


def _cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *argv: str | Path) -> None:
    """Runs `trialfolio` in the test process, offline, acknowledged for this command only, with
    its configuration and log directories in the test's own folder."""
    with monkeypatch.context() as patch:
        patch.setenv("HOME", str(tmp_path / "home"))
        for name in VARIABLES:
            patch.delenv(name, raising=False)
        patch.setenv(ACCEPT_VARIABLE, ACCEPT_VALUE)
        patch.setenv("TRIALFOLIO_CONFIG_DIR", str(tmp_path / "config"))
        patch.setenv("TRIALFOLIO_LOG_DIR", str(tmp_path / "logs"))
        patch.setattr(sys, "stdin", io.StringIO())
        patch.setattr(sys, "stdout", io.StringIO())
        stderr = io.StringIO()
        patch.setattr(sys, "stderr", stderr)
        code = trialfolio([str(arg) for arg in argv], clock=FixedClock())
    assert code == 0, stderr.getvalue()


def _schema_versions(out: Path, files: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """For each JSON file in `out`, its path, the version it holds, and the version of the schema
    whose region lists its fields. Each file is valid against that schema's model."""
    pages = {page.prefix: page.schema for page in manual_reference.SCHEMA_PAGES}
    models = {schema_file.name: schema_file.model for schema_file in SCHEMA_FILES}
    found: dict[str, tuple[str, str]] = {}
    for path in sorted(out.rglob("*.json")):
        relative = path.relative_to(out).as_posix()
        # A review's copies of its runs' files are listed with the runs' files.
        if path.name in UNSCHEMED or relative.startswith("inputs/"):
            continue
        (region,) = [
            region for pattern, region in files.items() if fnmatch.fnmatch(relative, pattern)
        ]
        schema = json.loads((manual_reference.SCHEMAS / pages[region]).read_text(encoding="utf-8"))
        models[pages[region]].model_validate_json(path.read_bytes())
        written = json.loads(path.read_bytes())["schema_version"]
        found[relative] = (written, schema["properties"]["schema_version"]["const"])
    return found


def test_each_file_the_commands_write_is_at_its_pages_schema_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The demo writes a screen run; the core writes the synthetic experiment, as no command does;
    # and a review compares two demo runs. None sends anything.
    _cli(monkeypatch, tmp_path, "demo", "--out", tmp_path / "demo")
    _cli(monkeypatch, tmp_path, "demo", "--out", tmp_path / "demo-again")
    write_synthetic_experiment(tmp_path / "experiment")
    configuration = tmp_path / "review.yaml"
    configuration.write_text(
        "kind: review\nschema_version: 1.0.0\ntitle: Two demo runs\nbaseline: demo\n"
        "results:\n  - label: demo\n    run: demo\n  - label: demo-again\n    run: demo-again\n",
        encoding="utf-8",
    )
    _cli(monkeypatch, tmp_path, "review", configuration, "--out", tmp_path / "review")

    run = _schema_versions(tmp_path / "demo", RUN_FILES)
    experiment = _schema_versions(tmp_path / "experiment", EXPERIMENT_FILES)
    review = _schema_versions(tmp_path / "review", REVIEW_FILES)

    assert {written for written, _ in run.values()} == {"1.0.0"}
    assert len(run) == 4
    assert {name.rsplit("/", 1)[-1] for name in experiment} == {
        "plan.json",
        "experiment.json",
        "session.json",
        "manifest.json",
        "started.json",
        "attempt.json",
        "authenticating.json",
    }
    assert all(written == expected for written, expected in run.values())
    assert all(written == expected for written, expected in experiment.values())
    assert review["manifest.json"][0] == review["manifest.json"][1]
