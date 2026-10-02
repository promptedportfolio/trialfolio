"""Installs the network guard in each Python subprocess the test suite starts.

The root conftest puts this directory first on PYTHONPATH, so Python imports this module at
startup. If the guard can't be installed, the process stops: site.py would report the error and
carry on without it. Python imports only the first sitecustomize it finds, so this one then runs
the one it shadows, such as Homebrew's, passing over any other copy of the guard.
"""

import importlib.machinery
import importlib.util
import os
import sys

try:
    import trialfolio_network_guard

    trialfolio_network_guard.install()
except BaseException as error:  # noqa: BLE001 - any failure stops the process.
    sys.stderr.write(f"network guard: not installed, so this process stops: {error!r}\n")
    sys.stderr.flush()
    os._exit(70)


def _run_shadowed() -> None:
    guard = "trialfolio_network_guard.py"
    path = [p for p in sys.path if not os.path.isfile(os.path.join(p or os.curdir, guard))]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", path)
    if spec is None or spec.loader is None:
        return
    try:
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
    except Exception as error:  # noqa: BLE001 - reported as site.py would report it.
        sys.stderr.write(
            "Error in sitecustomize; set PYTHONVERBOSE for traceback:\n"
            f"{type(error).__name__}: {error}\n"
        )


_run_shadowed()
