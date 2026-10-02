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

    trialfolio_network_guard.install(
        os.environ.get(trialfolio_network_guard.ALLOW_ENV, "").split(","),
        exit_on_refusal=True,
    )
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
    # Registered as Python's import would register it, so `import sitecustomize` gives it, and
    # code in it can find its own module.
    this = sys.modules[__name__]
    module = importlib.util.module_from_spec(spec)
    sys.modules["sitecustomize"] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - reported as site.py would report it.
        sys.modules["sitecustomize"] = this
        if sys.flags.verbose:
            sys.excepthook(type(error), error, error.__traceback__)
        else:
            sys.stderr.write(
                "Error in sitecustomize; set PYTHONVERBOSE for traceback:\n"
                f"{type(error).__name__}: {error}\n"
            )


_run_shadowed()
