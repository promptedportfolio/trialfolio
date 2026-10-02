"""Installs the network guard in each Python subprocess the test suite starts.

The root conftest puts this directory first on PYTHONPATH, so Python imports this module at
startup, unless a subprocess runs with -I, -E, or -S. Python imports only the first
sitecustomize it finds, so this one then runs the one it shadows, such as Homebrew's.
"""

import importlib.machinery
import importlib.util
import os
import sys
from types import ModuleType

_here = os.path.dirname(os.path.realpath(__file__))


def _load(spec: importlib.machinery.ModuleSpec | None) -> ModuleType:
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_guard_path = os.path.join(os.path.dirname(_here), "network_guard.py")
_load(
    importlib.util.spec_from_file_location("trialfolio_test_network_guard", _guard_path)
).install()

_rest = [p for p in sys.path if os.path.realpath(p or os.curdir) != _here]
_shadowed = importlib.machinery.PathFinder.find_spec("sitecustomize", _rest)
if _shadowed is not None:
    _load(_shadowed)
