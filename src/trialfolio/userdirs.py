"""The per-user directories: the configuration directory, which holds the license acknowledgment
record, and the log directory, for commands without an output directory (docs/contracts.md,
license acknowledgment, and logging and local diagnostics).

Each follows the same pattern: Trial Folio's own environment variable, if it's set and not empty,
and otherwise each platform's conventional place. On Linux, and any other system that isn't
macOS or Windows, that's the XDG base directory, whose variable counts only when it holds an
absolute path, as the XDG Base Directory Specification says.
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final

CONFIG_DIRECTORY_VARIABLE: Final = "TRIALFOLIO_CONFIG_DIR"
LOG_DIRECTORY_VARIABLE: Final = "TRIALFOLIO_LOG_DIR"

_NAME: Final = "trialfolio"


def config_directory(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """The per-user configuration directory: `TRIALFOLIO_CONFIG_DIR`; or
    `$XDG_CONFIG_HOME/trialfolio` or `~/.config/trialfolio` on Linux;
    `~/Library/Application Support/trialfolio` on macOS; `%APPDATA%\\trialfolio` on Windows."""
    chosen = environ.get(CONFIG_DIRECTORY_VARIABLE)
    if chosen:
        return Path(chosen)
    if platform == "darwin":
        return _home(environ) / "Library" / "Application Support" / _NAME
    if platform == "win32":
        return _windows(environ, "APPDATA", ("AppData", "Roaming")) / _NAME
    return _xdg(environ, "XDG_CONFIG_HOME", (".config",)) / _NAME


def log_directory(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """The per-user log directory: `TRIALFOLIO_LOG_DIR`; or `$XDG_STATE_HOME/trialfolio/logs` or
    `~/.local/state/trialfolio/logs` on Linux; `~/Library/Logs/trialfolio` on macOS;
    `%LOCALAPPDATA%\\trialfolio\\logs` on Windows."""
    chosen = environ.get(LOG_DIRECTORY_VARIABLE)
    if chosen:
        return Path(chosen)
    if platform == "darwin":
        return _home(environ) / "Library" / "Logs" / _NAME
    if platform == "win32":
        return _windows(environ, "LOCALAPPDATA", ("AppData", "Local")) / _NAME / "logs"
    return _xdg(environ, "XDG_STATE_HOME", (".local", "state")) / _NAME / "logs"


def _home(environ: Mapping[str, str]) -> Path:
    # Path.home() reads HOME from os.environ; the caller's environment is the one that counts.
    home = environ.get("HOME") or environ.get("USERPROFILE")
    return Path(home) if home else Path.home()


def _xdg(environ: Mapping[str, str], variable: str, fallback: tuple[str, ...]) -> Path:
    chosen = environ.get(variable)
    if chosen and os.path.isabs(chosen):
        return Path(chosen)
    return _home(environ).joinpath(*fallback)


def _windows(environ: Mapping[str, str], variable: str, fallback: tuple[str, ...]) -> Path:
    chosen = environ.get(variable)
    return Path(chosen) if chosen else _home(environ).joinpath(*fallback)
