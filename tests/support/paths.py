"""The committed fixtures' directories, each under a name that says which it is.

TS-T03 moved here the paths the interface's tests imported from their conftest.
"""

from pathlib import Path
from typing import Final

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
"""`tests/fixtures/`."""

SCREEN_CONFIGS: Final = FIXTURES / "screen-configs"
"""The screen configurations, valid ones at the top, and invalid ones under `invalid/`."""

RESPONSES: Final = FIXTURES / "responses"
"""Portfolio123's responses, as the fake server sends them."""


def screen_config(name: str) -> Path:
    """The screen configuration `name`, in `screen-configs/`."""
    return SCREEN_CONFIGS / name
