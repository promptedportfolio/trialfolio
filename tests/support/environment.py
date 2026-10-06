"""The environment a test runs Trial Folio's CLI in: without the variables Trial Folio reads,
apart from `HOME`, which a test points at a temporary directory, so nothing on the machine
running the tests leaks in.
"""

from typing import Final

from trialfolio.acknowledgment import ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE

VARIABLES: Final = (
    "TRIALFOLIO_CONFIG_DIR",
    "TRIALFOLIO_LOG_DIR",
    "TRIALFOLIO_LOG_LEVEL",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    ACCEPT_VARIABLE,
    API_ID_VARIABLE,
    API_KEY_VARIABLE,
    "SSLKEYLOGFILE",
)
"""The variables Trial Folio reads, which each test starts without, apart from `HOME`."""
