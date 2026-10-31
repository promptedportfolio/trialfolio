"""Reading a ranking snapshot configuration enforces docs/contracts.md's ranking snapshot
configuration rules.

Traces to release 0.4.0's test pairing: the snapshot example, `ranking-snapshot-configs/
example.yaml`, byte for byte (R04-AC08); and each file in tests/fixtures/ranking-snapshot-
configs/invalid/, one for each rule of the snapshot configuration and of every configuration
file, fails with `config.invalid`, and the message names the offending key, never its value (the
invalid ranking cases). R04-T05 wrote them. TS-T06 added the check, the other kinds' (docs/
test-refactoring.md, copies that check less, item 6), that no value of 20 characters or more
in the file is in the message. `trialfolio run` takes a snapshot configuration from
R04-T10, which runs `misspelled-key.yaml` and `unquoted-system.yaml` through the CLI.
"""

import re
from pathlib import Path

import pytest

from tests.support.contract_checks import (
    Rejection,
    assert_names_its_key_never_its_value,
    header,
)
from tests.support.paths import SCREEN_CONFIGS, SNAPSHOT_CONFIGS
from trialfolio.configuration import read_ranking_snapshot_configuration, read_run_configuration
from trialfolio.contracts.ranking_snapshot_configuration import RankingSnapshotConfiguration

REPO_ROOT = Path(__file__).resolve().parents[2]
INVALID = SNAPSHOT_CONFIGS / "invalid"


def documented_example() -> str:
    contracts = (REPO_ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("### Ranking snapshot configuration") :]
    found = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert found, "docs/contracts.md has no snapshot configuration example"
    return found.group(1)


def read(content: bytes | str) -> RankingSnapshotConfiguration:
    if isinstance(content, str):
        content = content.encode()
    return read_ranking_snapshot_configuration(content, "snapshot.yaml")


rejection = Rejection(read_ranking_snapshot_configuration, "snapshot.yaml")


def test_the_documented_example_reads_as_documented() -> None:
    assert read(documented_example()) == RankingSnapshotConfiguration(
        kind="ranking-snapshot", schema_version="1.0.0", system="Value and momentum"
    )


def test_the_example_fixture_is_the_documented_example() -> None:
    assert (SNAPSHOT_CONFIGS / "example.yaml").read_text(encoding="utf-8") == documented_example()


@pytest.mark.parametrize(
    ("name", "system"),
    [("api-ranking-system.yaml", "ApiRankingSystem"), ("canaries.yaml", "canary-system-4d7a2c19")],
)
def test_each_fixture_reads(name: str, system: str) -> None:
    assert read((SNAPSHOT_CONFIGS / name).read_bytes()).system == system


@pytest.mark.parametrize("path", sorted(INVALID.glob("*.yaml")), ids=lambda path: path.stem)
def test_invalid_configuration_is_rejected_naming_its_key_never_its_value(path: Path) -> None:
    message = rejection(path.read_bytes(), path.name)

    assert_names_its_key_never_its_value(path, message)
    # Nor is the value inside a longer name: no name a snapshot's message gives holds one.
    value = header(path.read_text(encoding="utf-8"), "Value")
    assert value == "-" or value not in message


def test_every_invalid_case_is_in_its_readme() -> None:
    readme = (INVALID / "README.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([a-z0-9.-]+)\.yaml` \|", readme, re.MULTILINE))

    assert listed == {path.stem for path in INVALID.glob("*.yaml")}


@pytest.mark.parametrize(
    "written", ['"Value and momentum"', "|-\n  Value and momentum", ">-\n  Value and momentum"]
)
def test_the_system_may_be_in_double_quotes_or_a_block_scalar(written: str) -> None:
    content = documented_example().replace("'Value and momentum'", written, 1)

    assert read(content).system == "Value and momentum"


def test_a_name_holding_a_hash_is_read_whole_in_quotes() -> None:
    """Without quotes, YAML would read `#2` as a comment, and name another system."""
    content = documented_example().replace("'Value and momentum'", "'Core Combo #2'", 1)

    assert read(content).system == "Core Combo #2"


def test_a_missing_kind_names_the_snapshot_kind() -> None:
    message = rejection("schema_version: 1.0.0\nsystem: 'Value and momentum'\n")

    assert "A ranking-snapshot configuration has `kind: ranking-snapshot`." in message


def test_a_screen_configuration_is_not_a_snapshot() -> None:
    content = (SCREEN_CONFIGS / "formula.yaml").read_bytes()

    assert "`kind` must be ranking-snapshot." in rejection(content)


def test_run_reads_a_snapshot_configuration() -> None:
    """`trialfolio run` takes `kind: ranking-snapshot` from R04-T10, which builds a snapshot's
    run. R04-T05 held that its reader refused the kind until then, naming the two kinds it ran."""
    configuration = read_run_configuration(
        documented_example().encode(), "snapshot.yaml", "snapshot.yaml"
    )

    assert configuration == read(documented_example())
