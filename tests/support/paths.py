"""The repository's root, and the committed fixtures' directories, each under a name that says which
it is.

TS-T03 moved here the paths the interface's tests imported from their conftest, and TS-T04 the
other modules' copies, in which `FIXTURES` meant `tests/fixtures/` or, in some, one of its
directories.
"""

from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
"""The repository's root, where `pyproject.toml` is."""

FIXTURES: Final = ROOT / "tests" / "fixtures"
"""`tests/fixtures/`."""

SCREEN_CONFIGS: Final = FIXTURES / "screen-configs"
"""The screen configurations, valid ones at the top, and invalid ones under `invalid/`."""

EXPERIMENT_CONFIGS: Final = FIXTURES / "experiment-configs"
"""The experiment configurations, valid ones at the top, revisions under `revisions/`, and invalid
ones under `invalid/`."""

RANKING_DEFINITIONS: Final = EXPERIMENT_CONFIGS / "ranking"
"""The ranking definitions the experiment and screen configurations name, and invalid ones under
`invalid/`."""

REVIEW_CONFIGS: Final = FIXTURES / "review-configs"
"""The review configurations, valid ones at the top, and invalid ones under `invalid/`."""

SNAPSHOT_CONFIGS: Final = FIXTURES / "ranking-snapshot-configs"
"""The ranking snapshot configurations, valid ones at the top, and invalid ones under
`invalid/`."""

RESPONSES: Final = FIXTURES / "responses"
"""Portfolio123's responses, as the fake server sends them."""


def screen_config(name: str) -> Path:
    """The screen configuration `name`, in `screen-configs/`."""
    return SCREEN_CONFIGS / name
