"""Loads the network guard's plugin for any pytest run in the repository, whichever paths it
collects (P-12).

pyproject.toml's addopts loads it first, with -p. This file loads it for a run without them, such
as one with -o addopts=. A run with another configuration file has no pythonpath setting to find
the plugin, so it fails here instead of running unguarded.
"""

pytest_plugins = ["trialfolio_network_guard_plugin"]
