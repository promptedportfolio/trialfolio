"""The per-user directories are where docs/contracts.md puts them: Trial Folio's own variable, and
otherwise each platform's conventional place.

Traces to docs/contracts.md, license acknowledgment (the record's configuration directory) and
logging and local diagnostics (the per-user log directory), and to R01-T14's rules there: a Trial
Folio variable counts only when it isn't empty, and an XDG variable only when it's an absolute
path. Each test passes the environment and the platform, so every platform's rule is checked on
any platform, against the literal paths the contract lists.
"""

import sys
from pathlib import Path, PureWindowsPath

import pytest

from trialfolio.userdirs import config_directory, log_directory

HOME = "/home/alice"
WINDOWS_HOME = r"C:\Users\alice"

POSIX_DEFAULTS = {
    ("linux", "config"): "/home/alice/.config/trialfolio",
    ("linux", "log"): "/home/alice/.local/state/trialfolio/logs",
    ("darwin", "config"): "/home/alice/Library/Application Support/trialfolio",
    ("darwin", "log"): "/home/alice/Library/Logs/trialfolio",
}
"""Each default outside Windows, for `HOME=/home/alice`."""

DIRECTORY = {"config": config_directory, "log": log_directory}
OVERRIDE = {"config": "TRIALFOLIO_CONFIG_DIR", "log": "TRIALFOLIO_LOG_DIR"}
XDG = {"config": "XDG_CONFIG_HOME", "log": "XDG_STATE_HOME"}
XDG_PATH = {"config": "/xdg/config/trialfolio", "log": "/xdg/state/trialfolio/logs"}
"""Where each directory is with `XDG_CONFIG_HOME=/xdg/config` or `XDG_STATE_HOME=/xdg/state`."""

KINDS = pytest.mark.parametrize("kind", ["config", "log"])


@KINDS
@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_each_platform_has_its_default(kind: str, platform: str) -> None:
    assert DIRECTORY[kind]({"HOME": HOME}, platform) == Path(POSIX_DEFAULTS[platform, kind])


@KINDS
def test_another_system_follows_linux(kind: str) -> None:
    # Any system that isn't macOS or Windows takes the XDG base directories.
    assert DIRECTORY[kind]({"HOME": HOME}, "freebsd14") == Path(POSIX_DEFAULTS["linux", kind])


@pytest.mark.parametrize(
    ("kind", "variable", "value", "expected"),
    [
        ("config", "APPDATA", r"D:\Roaming", r"D:\Roaming\trialfolio"),
        ("config", None, None, r"C:\Users\alice\AppData\Roaming\trialfolio"),
        ("log", "LOCALAPPDATA", r"D:\Local", r"D:\Local\trialfolio\logs"),
        ("log", None, None, r"C:\Users\alice\AppData\Local\trialfolio\logs"),
    ],
    ids=["appdata", "config-without-appdata", "localappdata", "log-without-localappdata"],
)
def test_windows_takes_its_application_data_directories(
    kind: str, variable: str | None, value: str | None, expected: str
) -> None:
    environ = {"USERPROFILE": WINDOWS_HOME}
    if variable is not None and value is not None:
        environ[variable] = value

    found = DIRECTORY[kind](environ, "win32")

    # Read as a Windows path, so the check holds on any platform.
    assert PureWindowsPath(found) == PureWindowsPath(expected)


@KINDS
@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_trial_folios_variable_comes_first(kind: str, platform: str) -> None:
    environ = {
        "HOME": HOME,
        "USERPROFILE": WINDOWS_HOME,
        XDG[kind]: "/xdg/elsewhere",
        OVERRIDE[kind]: "/srv/trialfolio",
    }

    assert DIRECTORY[kind](environ, platform) == Path("/srv/trialfolio")


@KINDS
def test_an_empty_trial_folio_variable_counts_as_unset(kind: str) -> None:
    environ = {"HOME": HOME, OVERRIDE[kind]: ""}

    assert DIRECTORY[kind](environ, "linux") == Path(POSIX_DEFAULTS["linux", kind])


@pytest.mark.skipif(sys.platform == "win32", reason="os.path.isabs reads the host's paths")
@KINDS
def test_an_absolute_xdg_variable_counts_on_linux(kind: str) -> None:
    value = "/xdg/config" if kind == "config" else "/xdg/state"

    assert DIRECTORY[kind]({"HOME": HOME, XDG[kind]: value}, "linux") == Path(XDG_PATH[kind])


@KINDS
@pytest.mark.parametrize("value", ["relative/dir", ""], ids=["relative", "empty"])
def test_an_xdg_variable_that_isnt_absolute_is_ignored(kind: str, value: str) -> None:
    environ = {"HOME": HOME, XDG[kind]: value}

    assert DIRECTORY[kind](environ, "linux") == Path(POSIX_DEFAULTS["linux", kind])


@KINDS
def test_macos_ignores_the_xdg_variables(kind: str) -> None:
    environ = {"HOME": HOME, XDG[kind]: "/xdg/elsewhere"}

    assert DIRECTORY[kind](environ, "darwin") == Path(POSIX_DEFAULTS["darwin", kind])
