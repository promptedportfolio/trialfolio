"""`trialfolio run` with an experiment's configuration writes each succeeded case's normalized
tables, `metrics.csv` and then `settings.csv`, in `cases/<case_id>/normalized/`, right after its
attempt record and before the next case's first write. Their rows are labeled with the case's
`case_id`, and equal those of a screen run with the same settings and response, apart from
`original_key`, `original_value`, and `source_artifact`, which come from the configuration of the
plan the attempt ran under. A case whose response fails validation has no tables. A resume writes
the `settings.csv` a stopped run didn't, and its manifest names the installed parser for the
case's response, also after a revision whose only change is Trial Folio's version.

Traces to R03-AC18, and to docs/contracts.md, an experiment's normalized tables (when they're
written, the label, `original_key` and `original_value`, `source_artifact`, tables a run didn't
write, and which parser wrote them), and normalized tables (R01-AC14's format rules). Each
experiment is written with the experiment builder, through the CLI's entry function in the test
process, over the fake server; the screen runs it's compared with are written with the run
builder. Storage faults record the order of the writes, and stop a run at a case's
`settings.csv`, and the package versions double reports another version of Trial Folio for a
first run.
"""

import codecs
import csv
import hashlib
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, get_args

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import ExperimentBuilder, experiment_config, returns
from tests.support.package_versions import fake_distribution
from tests.support.run_builder import Run, RunBuilder
from tests.support.storage_faults import FaultyStores
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.common import FlagCode, UnavailableReason
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import ExperimentPlanCase
from trialfolio.contracts.experiment_record import ExperimentRecord, SessionRecord
from trialfolio.contracts.manifest_parts import ParserVersion
from trialfolio.normalization import LAYOUT, LAYOUT_VERSION, PARSER_VERSION
from trialfolio.planning import build_experiment_plan, installed_versions
from trialfolio.storage import ArtifactStore, LocalArtifactStore

EXAMPLE = experiment_config("example.yaml")

ANSWERS: Final = (
    "complete.json",
    "missing-metrics.json",
    "changed-metrics.json",
    "coverage-mismatch.json",
    "complete.json",
)
"""The response each of `example.yaml`'s cases gets, in the plan's order: `baseline`,
`liquidity-100m`, `holdings-50`, `rebalance-weeks-1`, and `slippage-050`. They differ, so a
case's tables can only be drawn from its own response."""

METRICS_COLUMNS: Final = (
    "label",
    "subject",
    "metric_id",
    "source_label",
    "value",
    "unit",
    "source_decimals",
    "availability",
    "unavailable_reason",
    "origin",
    "provenance",
    "period_start",
    "period_end",
    "benchmark",
    "source_artifact",
    "source_location",
)
"""`metrics.csv`'s columns, in docs/contracts.md's order, as written by hand."""

SETTINGS_COLUMNS: Final = (
    "label",
    "setting",
    "category",
    "critical",
    "value",
    "unit",
    "interpretation",
    "provenance",
    "inference_rule",
    "original_key",
    "original_value",
    "source_artifact",
    "flags",
)
"""`settings.csv`'s columns, in docs/contracts.md's order, as written by hand."""

OWN_COLUMNS: Final = ("original_key", "original_value", "source_artifact")
"""The columns a case's rows take from its experiment's records, not from a screen run's."""

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

type Builder = ExperimentBuilder[Outcome]
type Rows = list[dict[str, str]]


def cases_of(path: Path) -> tuple[ExperimentPlanCase, ...]:
    """The planned cases of a new experiment of the configuration at `path`, in order."""
    configuration = read_experiment_configuration(path.read_bytes(), str(path))
    return build_experiment_plan(configuration, installed_versions()).cases


def case_named(path: Path, key: str) -> ExperimentPlanCase:
    return next(case for case in cases_of(path) if case.case_key == key)


def written(
    cli: Cli,
    experiments: Builder,
    path: Path = EXAMPLE,
    answers: tuple[str, ...] = ANSWERS,
    *,
    name: str = "experiment",
    store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
) -> Path:
    """Writes the experiment `path` gives into `name`, each case answered with its response in
    `answers`, every case succeeding, and returns its directory."""
    cli.ready()
    out = cli.tmp / name
    sends = [returns(answer) for answer in answers]
    outcome = experiments.run(path, out, sends=sends, store_factory=store_factory)
    assert outcome.exit_code == 0, outcome.stderr
    return out


def tables(out: Path, case_id: str) -> Path:
    return out / "cases" / case_id / "normalized"


def rows(path: Path) -> Rows:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))


def settings_of(out: Path, case_id: str) -> dict[str, dict[str, str]]:
    """The case's `settings.csv` rows, by setting."""
    return {row["setting"]: row for row in rows(tables(out, case_id) / "settings.csv")}


def apart_from_own(table: Rows) -> Rows:
    return [{name: v for name, v in row.items() if name not in OWN_COLUMNS} for row in table]


def artifact_id(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def response_of(out: Path, case_id: str) -> Path:
    (response,) = (out / "cases" / case_id / "attempts").glob("*/response.json")
    return response


def follows_the_format_rules(path: Path, columns: tuple[str, ...]) -> Rows:
    """The table's rows, once its bytes are checked against R01-AC14's format rules: UTF-8
    without a byte-order mark, `\\n` line endings, the documented header, and RFC 4180 quoting
    that Python's `csv` module reads back strictly, with every column in each row."""
    content = path.read_bytes()
    assert not content.startswith(codecs.BOM_UTF8)
    text = content.decode("utf-8")
    assert text.endswith("\n")
    assert "\r" not in text
    header, *body = csv.reader(io.StringIO(text, newline=""), strict=True)
    assert tuple(header) == columns
    assert body != []
    assert all(len(row) == len(columns) for row in body)
    return [dict(zip(columns, row, strict=True)) for row in body]


def write_order(published: list[str], case_id: str) -> tuple[int, int, int]:
    """Where the case's attempt record, `metrics.csv`, and `settings.csv` are in the order the
    store published the files."""
    case = f"cases/{case_id}/"
    (attempt,) = (
        place
        for place, path in enumerate(published)
        if path.startswith(f"{case}attempts/") and path.endswith("/attempt.json")
    )
    return (
        attempt,
        published.index(f"{case}normalized/metrics.csv"),
        published.index(f"{case}normalized/settings.csv"),
    )


# When the tables are written, and their label


def test_each_succeeded_case_has_its_tables_right_after_its_attempt_record(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    out = written(cli, experiments, store_factory=faults)

    published = faults.published
    cases = cases_of(EXAMPLE)
    for place, case in enumerate(cases):
        attempt, metrics, settings = write_order(published, case.case_id)
        assert (metrics, settings) == (attempt + 1, attempt + 2)
        # Before the next case's first write, or the session's report after the last case.
        following = published[settings + 1]
        if place + 1 < len(cases):
            assert following.startswith(f"cases/{cases[place + 1].case_id}/attempts/")
        else:
            assert following == "sessions/1/report.html"
        directory = tables(out, case.case_id)
        assert sorted(path.name for path in directory.iterdir()) == ["metrics.csv", "settings.csv"]
        for name in ("metrics.csv", "settings.csv"):
            assert {row["label"] for row in rows(directory / name)} == {case.case_id}


def test_a_cases_rows_equal_a_screen_runs_with_the_same_settings_and_response(
    cli: Cli, experiments: Builder
) -> None:
    out = written(cli, experiments)
    builder = RunBuilder(cli.tmp / "runs-home")
    compared = {
        # The baseline's settings are formula.yaml's, and holdings-50's are holdings-50.yaml's.
        "baseline": builder.run(Run("formula.yaml", ANSWERS[0]), cli.tmp / "formula"),
        "holdings-50": builder.run(Run("holdings-50.yaml", ANSWERS[2]), cli.tmp / "holdings-50"),
    }

    for key, run in compared.items():
        case = case_named(EXAMPLE, key)
        for name in ("metrics.csv", "settings.csv"):
            case_rows = rows(tables(out, case.case_id) / name)
            run_rows = rows(run / "normalized" / name)
            # The label too: the case's case_id is the screen run's.
            assert apart_from_own(case_rows) == apart_from_own(run_rows)
        # The case's key paths are the experiment configuration's: the baseline's key for a
        # setting it takes from the baseline, where the screen run has its top-level key.
        case_settings = settings_of(out, case.case_id)
        for run_row in rows(run / "normalized" / "settings.csv"):
            setting = run_row["setting"]
            if key == "holdings-50" and setting == "max_holdings":
                continue  # The variant's change, which the next test checks.
            expected = f"baseline.{run_row['original_key']}" if run_row["original_key"] else ""
            assert case_settings[setting]["original_key"] == expected


# original_key, original_value, and source_artifact


def test_original_key_is_the_key_path_in_the_plans_configuration(
    cli: Cli, experiments: Builder
) -> None:
    out = written(cli, experiments)

    expected = {
        ("baseline", "max_holdings"): ("baseline.max_holdings", "25"),
        ("holdings-50", "max_holdings"): ("variants.max_holdings[0].value", "50"),
        ("holdings-50", "rules"): ("baseline.rules", "- 'AvgDailyTot(30) > 1000000'"),
        ("liquidity-100m", "rules"): ("variants.rules[0].with", "'AvgDailyTot(30) > 100000000'"),
        ("liquidity-100m", "max_holdings"): ("baseline.max_holdings", "25"),
        # The default variant's rebalance_weeks, which no key of the file writes.
        ("rebalance-weeks-1", "rebalance_weeks"): ("", ""),
        ("slippage-050", "slippage_percent"): ("variants.slippage_percent[0].value", "0.5"),
    }
    for (key, setting), (original_key, original_value) in expected.items():
        row = settings_of(out, case_named(EXAMPLE, key).case_id)[setting]
        assert (row["original_key"], row["original_value"]) == (original_key, original_value)
    weeks = settings_of(out, case_named(EXAMPLE, "rebalance-weeks-1").case_id)["rebalance_weeks"]
    assert weeks["value"] == "1"


def test_an_added_rules_original_key_is_the_variants_add(cli: Cli, experiments: Builder) -> None:
    path = experiment_config("no-microcaps.yaml")
    out = written(cli, experiments, path, ("complete.json", "complete.json"))

    assert [case.case_key for case in cases_of(path)] == ["baseline", "no-microcaps"]
    rules = settings_of(out, case_named(path, "no-microcaps").case_id)["rules"]
    assert (rules["original_key"], rules["original_value"]) == (
        "variants.rules[0].add",
        "'MktCap > 300'",
    )
    assert rules["value"] == '["AvgDailyTot(30) > 1000000", "MktCap > 300"]'
    baseline = settings_of(out, case_named(path, "baseline").case_id)["rules"]
    assert baseline["original_key"] == "baseline.rules"


def test_original_value_is_the_text_in_the_file(cli: Cli, experiments: Builder) -> None:
    path = experiment_config("written-differently.yaml")
    out = written(cli, experiments, path)

    baseline = settings_of(out, case_named(path, "baseline").case_id)
    slippage = baseline["slippage_percent"]
    assert (slippage["original_key"], slippage["original_value"], slippage["value"]) == (
        "baseline.slippage_percent",
        "0.250",
        "0.25",
    )
    assert baseline["start_date"]["original_value"] == "'2016-01-01'"
    assert baseline["universe"]["original_value"] == '"SP500"'
    assert baseline["benchmark"]["original_value"] == '"SPY"'
    variant = settings_of(out, case_named(path, "slippage-050").case_id)["slippage_percent"]
    assert (variant["original_key"], variant["original_value"], variant["value"]) == (
        "variants.slippage_percent[0].value",
        "0.50",
        "0.5",
    )


def test_source_artifact_is_the_plans_configuration_and_the_cases_response(
    cli: Cli, experiments: Builder
) -> None:
    out = written(cli, experiments)

    configuration = artifact_id(out / "plans/1/configuration.yaml")
    for case in cases_of(EXAMPLE):
        directory = tables(out, case.case_id)
        assert {row["source_artifact"] for row in rows(directory / "settings.csv")} == {
            configuration
        }
        response = artifact_id(response_of(out, case.case_id))
        assert {row["source_artifact"] for row in rows(directory / "metrics.csv")} == {response}


# A response that fails validation


def test_a_case_answered_with_an_invalid_structure_has_no_tables_and_is_failed(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    answers = ["complete.json"] * 5
    answers[2] = "invalid-structure.json"  # holdings-50's

    outcome = experiments.run(EXAMPLE, out, sends=[returns(name) for name in answers])

    assert outcome.exit_code == 6, outcome.stderr
    error = outcome.error
    assert error["code"] == "execution.partial"
    assert "`holdings-50`, failed (provider.response_invalid)" in error["message"]
    holdings = case_named(EXAMPLE, "holdings-50")
    assert not tables(out, holdings.case_id).exists()
    # Its response was saved, and every other case has its tables.
    assert response_of(out, holdings.case_id).is_file()
    for case in cases_of(EXAMPLE):
        if case != holdings:
            assert (tables(out, case.case_id) / "settings.csv").is_file()
    outcomes = {case["case_key"]: case["outcome"] for case in outcome.cases}
    assert outcomes["holdings-50"] == "failed"
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert (manifest.counts.cases.succeeded, manifest.counts.cases.failed) == (4, 1)
    listed = {artifact.path for artifact in manifest.artifacts}
    assert not any(path.startswith(f"cases/{holdings.case_id}/normalized/") for path in listed)


# The tables a stopped run didn't write


@dataclass(frozen=True)
class Stopped:
    """A run of `example.yaml` that a storage fault stopped at a case's `settings.csv`."""

    out: Path
    case: ExperimentPlanCase
    """The case whose `settings.csv` the fault left out, `rebalance-weeks-1`."""
    metrics: bytes
    """The case's `metrics.csv`, which the run wrote before the fault."""
    received: int
    """How many requests the server had received when the run stopped."""

    @property
    def directory(self) -> Path:
        return tables(self.out, self.case.case_id)


def stop_at_the_settings_table(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    versions: Path | None = None,
) -> Stopped:
    """Runs `example.yaml` with a storage fault at `rebalance-weeks-1`'s `settings.csv`, so it
    stops at the fourth case's tables, and the fifth is never sent; checks that it left only the
    case's `metrics.csv`, with `versions`, when it's given, on the path, as the installed
    packages, so the session records another version of Trial Folio; and gives what it left."""
    out = cli.tmp / "experiment"
    case = case_named(EXAMPLE, "rebalance-weeks-1")  # Its response's coverage is flagged.
    faults.fail_os(f"{case.case_id}/settings.csv")
    sends = [returns(name) for name in ANSWERS[:4]]
    with monkeypatch.context() as patch:
        if versions is not None:
            patch.syspath_prepend(versions)
        stopped = experiments.run(EXAMPLE, out, sends=sends, store_factory=faults)
    assert stopped.exit_code == 4, stopped.stderr
    assert stopped.error_code == "storage.write_failed"
    directory = tables(out, case.case_id)
    assert sorted(path.name for path in directory.iterdir()) == ["metrics.csv"]
    session = SessionRecord.model_validate_json((out / "sessions/1/session.json").read_bytes())
    assert (session.trialfolio_version == "0.2.9") is (versions is not None)
    metrics = (directory / "metrics.csv").read_bytes()
    return Stopped(out, case, metrics, len(cli.server.received))


def assert_completes_the_settings_table(cli: Cli, stopped: Stopped, reference: Path) -> None:
    """Only the last case was due, so the resume sent only it: the case whose `settings.csv` was
    missing isn't sent again, and its `settings.csv` is the one the same experiment, uninterrupted,
    wrote into `reference`, its `metrics.csv` is as the stopped run left it, and the resume's
    manifest names the installed parser for the case's response, and lists both tables."""
    out, case, directory = stopped.out, stopped.case, stopped.directory
    assert cli.server.requests()[stopped.received :] == ["POST /auth", "POST /screen/backtest"]
    assert len(list((out / "cases" / case.case_id / "attempts").iterdir())) == 1
    assert (directory / "metrics.csv").read_bytes() == stopped.metrics
    reference_tables = tables(reference, case.case_id)
    assert (directory / "settings.csv").read_bytes() == (
        reference_tables / "settings.csv"
    ).read_bytes()
    assert "coverage_mismatch" in (directory / "settings.csv").read_text(encoding="utf-8")
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/2/manifest.json").read_bytes()
    )
    entries = {artifact.path: artifact for artifact in manifest.artifacts}
    response = entries[response_of(out, case.case_id).relative_to(out).as_posix()]
    assert response.source is not None
    assert (response.source.format, response.source.parser_version) == (LAYOUT, PARSER_VERSION)
    assert manifest.parsers == (
        ParserVersion(layout=LAYOUT, layout_version=LAYOUT_VERSION, parser_version=PARSER_VERSION),
    )
    normalized = f"cases/{case.case_id}/normalized"
    assert entries[f"{normalized}/settings.csv"].artifact_id == artifact_id(
        directory / "settings.csv"
    )
    assert entries[f"{normalized}/metrics.csv"].artifact_id == artifact_id(
        directory / "metrics.csv"
    )


def test_a_resume_writes_the_settings_table_a_storage_fault_left_out(
    cli: Cli, experiments: Builder, faults: FaultyStores, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same experiment, uninterrupted, gives the tables the resume should complete.
    reference = written(cli, experiments, name="reference")
    stopped = stop_at_the_settings_table(cli, experiments, faults, monkeypatch)

    resumed = experiments.run(EXAMPLE, stopped.out, sends=[returns(ANSWERS[4])])

    assert resumed.exit_code == 0, resumed.stderr
    assert not (stopped.out / "plans/2").exists()
    assert_completes_the_settings_table(cli, stopped, reference)


def test_a_revision_for_another_version_writes_the_settings_table_a_storage_fault_left_out(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference = written(cli, experiments, name="reference")
    # The first run is another version of Trial Folio's, so the resume is a revision whose only
    # change is Trial Folio's version.
    versions = tmp_path / "earlier-trialfolio"
    versions.mkdir()
    fake_distribution(versions, "trialfolio", "0.2.9")
    stopped = stop_at_the_settings_table(cli, experiments, faults, monkeypatch, versions)

    resumed = experiments.run(
        EXAMPLE,
        stopped.out,
        "--revision-reason",
        "Upgraded Trial Folio.",
        sends=[returns(ANSWERS[4])],
    )

    assert resumed.exit_code == 0, resumed.stderr
    record = ExperimentRecord.model_validate_json(
        (stopped.out / "plans/2/experiment.json").read_bytes()
    )
    changes = record.plans[-1].changes
    assert changes is not None
    assert [change.package for change in changes.versions] == ["trialfolio"]
    assert (changes.parts, changes.cases_added, changes.cases_retired) == ((), (), ())
    assert_completes_the_settings_table(cli, stopped, reference)


def test_each_cases_tables_follow_the_format_rules(cli: Cli, experiments: Builder) -> None:
    out = written(cli, experiments)

    reasons = set(get_args(UnavailableReason))
    flag_codes = set(get_args(FlagCode))
    unavailable = 0
    flagged: set[str] = set()
    for case in cases_of(EXAMPLE):
        directory = tables(out, case.case_id)
        for row in follows_the_format_rules(directory / "metrics.csv", METRICS_COLUMNS):
            # An empty value only with its reason, and a reason only with an empty value.
            assert (row["value"] == "") == (row["availability"] == "unavailable")
            assert (row["value"] == "") == (row["unavailable_reason"] in reasons)
            assert row["unavailable_reason"] == "" or row["unavailable_reason"] in reasons
            unavailable += row["availability"] == "unavailable"
            for name in ("period_start", "period_end"):
                assert row[name] == "" or DATE.match(row[name])
            assert row["source_decimals"] == "" or row["source_decimals"].isdigit()
            if row["unit"] == "date" and row["value"]:
                assert DATE.match(row["value"])
        for row in follows_the_format_rules(directory / "settings.csv", SETTINGS_COLUMNS):
            assert row["value"] != ""
            assert row["critical"] in ("true", "false")
            assert (row["original_key"] == "") == (row["original_value"] == "")
            codes = set(filter(None, row["flags"].split(";")))
            assert codes <= flag_codes
            flagged |= codes
    # missing-metrics.json's and coverage-mismatch.json's cases exercise the rules for empty
    # values and flags.
    assert unavailable > 0
    assert "coverage_mismatch" in flagged
