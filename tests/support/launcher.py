"""The test launcher (release 0.1.0, test pairing): runs the CLI's entry function in a new Python
process, with the fake server's endpoint and a request timeout. It isn't a double, and installs
none: the client, the store, and the clock are the real ones.

The timeout is the installed command's 300 seconds, so success-path tests don't depend on how
fast the machine is, unless the test is about a timeout and sets 1 second, the shortest the
wrapper takes (docs/contracts.md, HTTP exchanges). The process's exit code, stdout, and stderr are
the command's.

A test runs `command(...)` with `subprocess`, or under the terminal, whenever the command may
reach the fake server. The new process inherits the test's environment, unless the test passes
another, so the network guard stays first on its `PYTHONPATH`. A test that needs storage or
socket faults calls the entry function in the test process instead.
"""

import sys
from pathlib import Path
from typing import Final

from trialfolio.provider import REQUEST_TIMEOUT_SECONDS

SHORTEST_TIMEOUT_SECONDS: Final = 1
"""The shortest request timeout the wrapper takes, for a test about a timeout."""

_ENTRY: Final = """
import sys

from trialfolio.cli import main

endpoint, timeout, *argv = sys.argv[1:]
sys.exit(main(argv, endpoint=endpoint, timeout=int(timeout)))
"""


def command(endpoint: str, *argv: str | Path, timeout: int = REQUEST_TIMEOUT_SECONDS) -> list[str]:
    """The command line that runs `trialfolio` with `argv`, the arguments after its name,
    against `endpoint`, such as the fake server's, with a request timeout of `timeout` seconds."""
    return [sys.executable, "-c", _ENTRY, endpoint, str(timeout), *(str(arg) for arg in argv)]
