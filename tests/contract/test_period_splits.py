"""Reading a configuration's period splits enforces docs/contracts.md's period splits rules.

Traces to R05-AC12, as release 0.5.0's test pairing gives it for `test_period_splits.py`: each
invalid split case fails with `config.invalid`, and the message names the key by its place, such
as `analysis.period_splits[1].date`, and the rule, never the label; a configuration 1.2.0 without
`analysis` reads as its 1.1.0 form; and the contracts example reads. The other tests trace to the
keys' rules in docs/contracts.md's period splits: any date, ten splits at most, labels compared
character for character, and splits that are no case's settings; and to R05-AC10, which keeps
every configuration releases 0.1.0 to 0.4.0 accept reading as it did, and to docs/contracts.md's
readers: 0.5.0's refuse each invalid file of 1.0.0 or 1.1.0 with 0.4.0's message, and a 1.2.0 file
by its 1.1.0 form's rules, an experiment's budget and ranking variants included, which the review
of R05-T05's pull request found no test checked. R05-T05 wrote them, with 0.5.0's readers,
`read_screen_configuration_v1_2` and `read_experiment_configuration_v1_2`, which `trialfolio run`
reads with from R05-T08. Until then, `run` reads with 0.4.0's readers, whose messages stay
0.4.0's, which the last tests check, as R05-T05's details give them (release 0.5.0's changes after
sign-off). The fixtures are tests/fixtures/screen-configs/hand-checkable-split.yaml,
tests/fixtures/experiment-configs/hand-checkable.yaml, and the invalid split cases beside each.
"""

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from tests.support.contract_checks import Rejection, assert_names_its_key_never_its_value
from tests.support.paths import EXPERIMENT_CONFIGS, ROOT, SCREEN_CONFIGS
from trialfolio.configuration import (
    read_experiment_configuration_v1_1,
    read_experiment_configuration_v1_2,
    read_screen_configuration_v1_1,
    read_screen_configuration_v1_2,
)
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfigurationV1_1,
    ExperimentConfigurationV1_2,
    configured_variants_v1_1,
)
from trialfolio.contracts.screen_configuration import (
    Analysis,
    PeriodSplit,
    ScreenConfigurationV1_1,
    ScreenConfigurationV1_2,
)

SPLIT_SCREEN = SCREEN_CONFIGS / "hand-checkable-split.yaml"
SPLIT_EXPERIMENT = EXPERIMENT_CONFIGS / "hand-checkable.yaml"
LABEL = "End of the example's first week"
SPLIT_BLOCK = """analysis:
  period_splits:
    - date: 2024-01-05
      label: 'End of the example''s first week'
"""

RULES = {
    "analysis-in-1.1.0": "needs schema_version 1.2.0, the first that declares period splits",
    "analysis-not-a-mapping": "input should be a valid dictionary or instance of Analysis",
    "analysis-unknown-key": "isn't a key this configuration accepts",
    "period-splits-missing": "is required",
    "period-splits-not-a-list": "must be a list",
    "period-splits-empty": "must hold at least 1 item",
    "period-splits-eleven": "must hold at most 10 items",
    "split-not-a-mapping": "input should be a valid dictionary or instance of PeriodSplit",
    "split-unknown-key": "isn't a key this configuration accepts",
    "split-date-missing": "is required",
    "split-label-missing": "is required",
    "split-date-not-a-date": "isn't a valid date",
    "split-date-with-time": "is a date with a time part",
    "split-date-number": "input should be a valid date",
    "split-dates-decreasing": "is earlier than the date before it",
    "split-dates-equal": "is the same as the date before it",
    "split-label-empty": "string should have at least 1 character",
    "split-label-whitespace": "is blank",
    "split-label-too-long": "string should have at most 200 characters",
    "split-label-number": "input should be a valid string",
    "split-labels-equal": "is the same as an earlier split's label",
    "analysis-in-baseline": "isn't a key of the baseline: an experiment's period splits apply",
    "analysis-as-variant": "isn't a setting a variant may change",
}
"""Each invalid split case's rule, as its message gives it after the key."""

SCREEN_CASES = sorted(
    path for path in (SCREEN_CONFIGS / "invalid").glob("*.yaml") if path.stem in RULES
)
EXPERIMENT_CASES = sorted(
    path for path in (EXPERIMENT_CONFIGS / "invalid").glob("*.yaml") if path.stem in RULES
)


def read_screen(content: bytes, name: str = "screen.yaml") -> ScreenConfigurationV1_2:
    configuration = read_screen_configuration_v1_2(
        content, name, SCREEN_CONFIGS / name
    ).configuration
    assert isinstance(configuration, ScreenConfigurationV1_2)
    return configuration


def read_experiment(content: bytes, name: str = "experiment.yaml") -> ExperimentConfigurationV1_2:
    configuration = read_experiment_configuration_v1_2(
        content, name, EXPERIMENT_CONFIGS / name
    ).configuration
    assert isinstance(configuration, ExperimentConfigurationV1_2)
    return configuration


def replaced(path: Path, old: str, new: str) -> bytes:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    return text.replace(old, new).encode()


screen_rejection = Rejection(
    lambda content, name: read_screen_configuration_v1_2(content, name, SPLIT_SCREEN),
    "screen.yaml",
)
experiment_rejection = Rejection(
    lambda content, name: read_experiment_configuration_v1_2(content, name, SPLIT_EXPERIMENT),
    "experiment.yaml",
)


def named_cases(text: str) -> set[str]:
    """The cases `text` names in backticks, without the file each changes, or a value in
    parentheses, such as `2024-02-30`."""
    return {
        name
        for name in re.findall(r"`([a-z0-9.-]+)`", text)
        if name[0].isalpha() and not name.endswith(".yaml")
    }


def readme_split_cases(directory: Path) -> set[str]:
    """The files the table of the period splits' section of `directory`'s README lists."""
    readme = (directory / "invalid" / "README.md").read_text(encoding="utf-8")
    section = readme.split("\n## Period splits, from 1.2.0", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `([a-z0-9.-]+)\.yaml` \|", section, re.MULTILINE))


def test_the_fixtures_are_the_invalid_split_cases_the_test_pairing_names() -> None:
    """Release 0.5.0's invalid split cases, by group: the screen's 21, and the experiment's 5.
    Each case the pairing names has its fixture and its rule here, and so does each file the
    READMEs' tables of the period splits list."""
    pairing = (ROOT / "docs" / "releases" / "0.5.0-return-analytics.md").read_text(encoding="utf-8")
    section = pairing[pairing.index("#### Invalid split cases") :]
    screen, experiment = section.split("\n- **Experiment configurations,**", 1)
    experiment = experiment[: experiment.index("\n\n")]
    screen = screen[screen.index("\n- **Screen configurations,**") :]

    assert {path.stem for path in SCREEN_CASES} == named_cases(screen)
    assert {path.stem for path in EXPERIMENT_CASES} == named_cases(experiment)
    assert named_cases(screen) | named_cases(experiment) == set(RULES)
    assert readme_split_cases(SCREEN_CONFIGS) == named_cases(screen)
    assert readme_split_cases(EXPERIMENT_CONFIGS) == named_cases(experiment)
    assert (len(SCREEN_CASES), len(EXPERIMENT_CASES)) == (21, 5)


@pytest.mark.parametrize(
    "path",
    [*SCREEN_CASES, *EXPERIMENT_CASES],
    ids=lambda path: f"{path.parent.parent.name}/{path.stem}",
)
def test_each_invalid_split_case_names_its_key_and_its_rule_never_a_label(path: Path) -> None:
    rejection = screen_rejection if path.is_relative_to(SCREEN_CONFIGS) else experiment_rejection
    content = path.read_text(encoding="utf-8")

    message = rejection(path.read_bytes(), path.name)

    assert_names_its_key_never_its_value(path, message)
    # One problem: the file breaks its own rule, and no other.
    (problem,) = message.splitlines()[1:]
    key = re.search(r"^# Key: (.+)$", content, re.MULTILINE)
    assert key is not None
    assert problem.startswith(f"- `{key.group(1)}` ")
    assert RULES[path.stem] in problem
    for label in re.findall(r"label: '((?:[^']|'')*)'", content):
        if label.strip():
            assert label.replace("''", "'") not in message


def test_the_contracts_example_reads() -> None:
    """docs/contracts.md's period splits example, in an experiment configuration 1.2.0, and the
    release's, which is the same."""
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("### Period splits") :]
    documented = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert documented is not None
    block = documented.group(1)
    release = (ROOT / "docs" / "releases" / "0.5.0-return-analytics.md").read_text(encoding="utf-8")
    assert block[block.index("analysis:") :] in release
    assert block.startswith("kind: experiment\nschema_version: 1.2.0\n")

    configuration = read_experiment(
        replaced(SPLIT_EXPERIMENT, SPLIT_BLOCK, block[block.index("analysis:") :])
    )

    assert configuration.analysis == Analysis(
        period_splits=(
            PeriodSplit(date=date(2012, 12, 31), label="End of the paper's sample"),
            PeriodSplit(date=date(2016, 6, 30), label="Publication"),
        )
    )


def test_the_hand_checkable_splits_read() -> None:
    split = PeriodSplit(date=date(2024, 1, 5), label=LABEL)

    screen = read_screen(SPLIT_SCREEN.read_bytes(), SPLIT_SCREEN.name)
    experiment = read_experiment(SPLIT_EXPERIMENT.read_bytes(), SPLIT_EXPERIMENT.name)

    assert screen.analysis == Analysis(period_splits=(split,))
    assert experiment.analysis == Analysis(period_splits=(split,))
    assert [variant.key for variant in configured_variants_v1_1(experiment)] == [
        "holdings-50",
        "rebalance-weeks-4",
    ]
    assert experiment.budget.provider_requests == 3


def test_a_screen_configuration_1_2_0_without_analysis_reads_as_its_1_1_0_form() -> None:
    without = replaced(SPLIT_SCREEN, SPLIT_BLOCK, "")

    configuration = read_screen(without)
    earlier = read_screen_configuration_v1_1(
        without.replace(b"schema_version: 1.2.0", b"schema_version: 1.1.0"),
        "screen.yaml",
        SPLIT_SCREEN,
    ).configuration

    assert isinstance(earlier, ScreenConfigurationV1_1)
    assert configuration.analysis is None
    assert configuration.model_dump(exclude={"schema_version", "analysis"}) == earlier.model_dump(
        exclude={"schema_version"}
    )
    assert list(ScreenConfigurationV1_2.model_fields) == [
        *ScreenConfigurationV1_1.model_fields,
        "analysis",
    ]


def test_an_experiment_configuration_1_2_0_without_analysis_reads_as_its_1_1_0_form() -> None:
    """Its cases too: a split is no case's setting, so each case's settings are its 1.1.0 form's,
    with splits or without."""
    without = replaced(SPLIT_EXPERIMENT, SPLIT_BLOCK, "")

    configuration = read_experiment(without)
    with_splits = read_experiment(SPLIT_EXPERIMENT.read_bytes())
    earlier = read_experiment_configuration_v1_1(
        without.replace(b"schema_version: 1.2.0", b"schema_version: 1.1.0"),
        "experiment.yaml",
        SPLIT_EXPERIMENT,
    ).configuration

    assert isinstance(earlier, ExperimentConfigurationV1_1)
    assert configuration.analysis is None
    assert configuration.model_dump(exclude={"schema_version", "analysis"}) == earlier.model_dump(
        exclude={"schema_version"}
    )
    cases = [variant.screen for variant in configured_variants_v1_1(earlier)]
    assert [variant.screen for variant in configured_variants_v1_1(configuration)] == cases
    assert [variant.screen for variant in configured_variants_v1_1(with_splits)] == cases
    assert list(ExperimentConfigurationV1_2.model_fields) == [
        *ExperimentConfigurationV1_1.model_fields,
        "analysis",
    ]


@pytest.mark.parametrize("path", [SPLIT_SCREEN, SPLIT_EXPERIMENT], ids=["screen", "experiment"])
def test_a_1_0_0_file_with_analysis_is_told_it_needs_1_2_0(path: Path) -> None:
    rejection = screen_rejection if path == SPLIT_SCREEN else experiment_rejection

    message = rejection(replaced(path, "schema_version: 1.2.0", "schema_version: 1.0.0"))

    assert message.splitlines()[1:] == [
        "- `analysis` needs schema_version 1.2.0, the first that declares period splits."
    ]


@pytest.mark.parametrize(
    "dates",
    [("2012-12-31",), ("2024-01-07",), ("2030-06-30",), ("2023-12-29", "2024-01-05", "2024-01-15")],
    ids=["before-the-dates", "a-sunday", "after-the-dates", "on-either-side"],
)
def test_a_split_may_be_on_any_date(dates: tuple[str, ...]) -> None:
    """A date outside the requested dates, or on a weekend, is flagged when the analyses are
    calculated, not refused here."""
    block = "analysis:\n  period_splits:\n" + "".join(
        f"    - date: {when}\n      label: 'Split {number}'\n" for number, when in enumerate(dates)
    )

    configuration = read_screen(replaced(SPLIT_SCREEN, SPLIT_BLOCK, block))

    assert configuration.analysis is not None
    splits = configuration.analysis.period_splits
    assert [split.date.isoformat() for split in splits] == list(dates)


def test_ten_splits_are_the_most() -> None:
    block = "analysis:\n  period_splits:\n" + "".join(
        f"    - date: '2024-01-{day:02d}'\n      label: 'Split {day}'\n" for day in range(1, 11)
    )

    configuration = read_screen(replaced(SPLIT_SCREEN, SPLIT_BLOCK, block))

    assert configuration.analysis is not None
    assert len(configuration.analysis.period_splits) == 10


def test_labels_are_compared_character_for_character() -> None:
    block = (
        "analysis:\n  period_splits:\n"
        "    - date: 2024-01-05\n      label: 'Publication'\n"
        "    - date: 2024-01-08\n      label: 'publication'\n"
        "    - date: 2024-01-10\n      label: 'Publication '\n"
    )

    configuration = read_screen(replaced(SPLIT_SCREEN, SPLIT_BLOCK, block))

    assert configuration.analysis is not None
    labels = [split.label for split in configuration.analysis.period_splits]
    assert labels == ["Publication", "publication", "Publication "]


def test_a_label_may_be_written_without_quotes() -> None:
    """A label is never sent, as a title isn't, so it may be a plain scalar."""
    configuration = read_screen(replaced(SPLIT_SCREEN, "'End of the example''s first week'", "End"))

    assert configuration.analysis is not None
    assert configuration.analysis.period_splits[0].label == "End"


def earlier_versions(directory: Path) -> list[Path]:
    """The valid configurations in `directory` of a version 0.4.0's readers read."""
    return [
        path
        for path in sorted(directory.glob("*.yaml"))
        if b"schema_version: 1.2.0" not in path.read_bytes()
    ]


@pytest.mark.parametrize("path", earlier_versions(SCREEN_CONFIGS), ids=lambda path: path.stem)
def test_each_screen_configuration_earlier_versions_accept_reads_as_it_did(path: Path) -> None:
    content = path.read_bytes()

    read = read_screen_configuration_v1_2(content, path.name, path)
    earlier = read_screen_configuration_v1_1(content, path.name, path)

    assert (read.configuration, read.definition, read.snapshot) == (
        earlier.configuration,
        earlier.definition,
        earlier.snapshot,
    )


@pytest.mark.parametrize("path", earlier_versions(EXPERIMENT_CONFIGS), ids=lambda path: path.stem)
def test_each_experiment_configuration_earlier_versions_accept_reads_as_it_did(
    path: Path,
) -> None:
    content = path.read_bytes()

    read = read_experiment_configuration_v1_2(content, path.name, path)
    earlier = read_experiment_configuration_v1_1(content, path.name, path)

    assert (read.configuration, read.definition, read.ranking_cases, read.snapshot) == (
        earlier.configuration,
        earlier.definition,
        earlier.ranking_cases,
        earlier.snapshot,
    )


type Reader = Callable[[bytes, str, Path], object]
"""A reader of 0.4.0's, given the file's bytes, its name, and its path."""


def rejected_by(reader: Reader, path: Path, content: bytes) -> str:
    return Rejection(lambda content, name: reader(content, name, path), path.name)(content)


READERS: dict[Path, tuple[Reader, Reader]] = {
    SCREEN_CONFIGS: (read_screen_configuration_v1_2, read_screen_configuration_v1_1),
    EXPERIMENT_CONFIGS: (read_experiment_configuration_v1_2, read_experiment_configuration_v1_1),
}
"""0.5.0's reader of each kind of configuration, and 0.4.0's, by the directory of its files."""
EARLIER_VERSION = re.compile(rb"^schema_version: (1\.0\.0|1\.1\.0)$", re.MULTILINE)


def invalid_earlier_versions() -> list[Path]:
    """The invalid configurations of version 1.0.0 or 1.1.0 that give no `analysis`, which only
    0.5.0's readers tell needs 1.2.0."""
    return [
        path
        for directory in READERS
        for path in sorted((directory / "invalid").glob("*.yaml"))
        if EARLIER_VERSION.search(path.read_bytes())
        and not re.search(rb"^analysis:", path.read_bytes(), re.MULTILINE)
    ]


def invalid_id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.stem}"


@pytest.mark.parametrize("path", invalid_earlier_versions(), ids=invalid_id)
def test_each_invalid_earlier_version_is_refused_as_0_4_0_s_readers_refuse_it(path: Path) -> None:
    """0.5.0's readers read 1.0.0 and 1.1.0 as 0.4.0's do (the readers), so each rule's message
    is 0.4.0's, a 1.0.0 file's form that needs 1.1.0 included."""
    reader, earlier = READERS[path.parent.parent]
    content = path.read_bytes()

    assert rejected_by(reader, path, content) == rejected_by(earlier, path, content)


@pytest.mark.parametrize(
    "path",
    [path for path in invalid_earlier_versions() if not path.stem.endswith("-in-1.0.0")],
    ids=invalid_id,
)
def test_each_invalid_file_as_1_2_0_is_refused_as_its_1_1_0_form_is(path: Path) -> None:
    """Version 1.2.0 has 1.1.0's keys and rules, its rules across keys included: an experiment's
    budget sends each case once, twice with a ranking definition, and its ranking variants need a
    baseline ranked by a definition or a snapshot; and a variant may change the ranking. Each
    file is read as each version, but those invalid in 1.0.0 alone, for a form that needs 1.1.0:
    the other 1.0.0 files' rules hold in 1.1.0 too."""
    reader, earlier = READERS[path.parent.parent]
    content = path.read_bytes()

    assert rejected_by(reader, path, EARLIER_VERSION.sub(b"schema_version: 1.2.0", content)) == (
        rejected_by(earlier, path, EARLIER_VERSION.sub(b"schema_version: 1.1.0", content))
    )


def test_an_experiment_with_splits_has_a_budget_for_its_cases() -> None:
    message = experiment_rejection(
        replaced(SPLIT_EXPERIMENT, "provider_requests: 3", "provider_requests: 2")
    )

    assert message.splitlines()[1:] == [
        (
            "- `budget.provider_requests` is less than the experiment's 3 cases. It must be at "
            "least the number of cases, so that each can be sent once."
        )
    ]


@pytest.mark.parametrize(
    ("reader", "path"),
    [
        (read_screen_configuration_v1_1, SPLIT_SCREEN),
        (read_experiment_configuration_v1_1, SPLIT_EXPERIMENT),
    ],
    ids=["screen", "experiment"],
)
def test_0_4_0_s_readers_refuse_1_2_0_by_its_version(reader: Reader, path: Path) -> None:
    """`trialfolio run` reads with them until R05-T08, so it refuses a 1.2.0 file by its version,
    rather than read it without its splits."""
    message = rejected_by(reader, path, path.read_bytes())

    assert message.splitlines()[1:] == [
        "- `schema_version` isn't a supported version. Supported versions: 1.0.0, 1.1.0."
    ]


@pytest.mark.parametrize(
    ("reader", "path", "key"),
    [
        (
            read_screen_configuration_v1_1,
            SCREEN_CONFIGS / "invalid" / "analysis-in-1.1.0.yaml",
            "analysis",
        ),
        (
            read_experiment_configuration_v1_1,
            EXPERIMENT_CONFIGS / "invalid" / "analysis-in-1.1.0.yaml",
            "analysis",
        ),
        (
            read_experiment_configuration_v1_1,
            EXPERIMENT_CONFIGS / "invalid" / "analysis-in-baseline.yaml",
            "baseline.analysis",
        ),
    ],
    ids=["screen", "experiment", "experiment-baseline"],
)
def test_0_4_0_s_readers_keep_their_message_for_analysis(
    reader: Reader, path: Path, key: str
) -> None:
    """They don't tell a user of `trialfolio run` to use a version `run` refuses."""
    content = path.read_bytes().replace(b"schema_version: 1.2.0", b"schema_version: 1.1.0")

    message = rejected_by(reader, path, content)

    assert message.splitlines()[1:] == [
        f"- `{key}` isn't a key this configuration accepts. Check its spelling."
    ]
