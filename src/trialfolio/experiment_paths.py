"""The paths of an experiment's output directory (docs/contracts.md, experiment output): the names
of the files in a plan's directory, `plans/<n>/`, and in a session's, `sessions/<s>/`, and of an
attempt's request and saved response, with the paths of a plan's and a session's files.

The names of an attempt's records, and its directory, are `attempts.py`'s, and the paths of a
case's normalized tables `normalization.py`'s, beside the code that writes them.
"""

from typing import Final

CONFIGURATION: Final = "configuration.yaml"
PLAN: Final = "plan.json"
EXPERIMENT_RECORD: Final = "experiment.json"
SESSION_RECORD: Final = "session.json"
REPORT: Final = "report.html"
MANIFEST: Final = "manifest.json"
REQUEST: Final = "request.json"
RESPONSE: Final = "response.json"
RESPONSE_RAW: Final = "response.raw"


def plan_path(plan: int, name: str) -> str:
    """`plans/<plan>/<name>`, relative to the output root."""
    return f"plans/{plan}/{name}"


def session_path(session: int, name: str) -> str:
    """`sessions/<session>/<name>`, relative to the output root."""
    return f"sessions/{session}/{name}"
