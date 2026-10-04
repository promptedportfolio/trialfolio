"""`trialfolio init`'s starter files: what a new workspace holds (docs/contracts.md, CLI behavior;
release 0.1.0, included scope).

A workspace is a folder for one user's configurations, runs, and reports. No command depends on
it: it's where the user starts, and Trial Folio never looks for it.

- `screen.yaml` is the documented example without its purpose, with comments on each key. Its
  settings resolve to the request Portfolio123 accepted in R01-T01.
- `README.md` says what the folder holds, and the next commands, with a link to the user guide
  at the version's release tag, which works once the version is tagged.
- `.gitignore` keeps credential files, and the runs and reports, which hold Portfolio123 data,
  out of Git, for a user who keeps the folder in a repository.

They're packaged in `init_data/`, with `.gitignore` as `gitignore`, so that no tool takes it for
the package's own.
"""

from importlib.resources import files
from typing import Final

CONFIGURATION: Final = "screen.yaml"
"""The starter configuration, which `trialfolio init` writes first, claiming the folder."""

_FILES: Final = (
    (CONFIGURATION, "screen.yaml"),
    ("README.md", "README.md"),
    (".gitignore", "gitignore"),
)
"""Each starter file's name in the workspace, and in `init_data/`, in the order they're written."""


def starter_files(trialfolio_version: str) -> tuple[tuple[str, bytes], ...]:
    """Each starter file's name and bytes, in the order `trialfolio init` writes them, with the
    configuration first. The README links to the user guide of `trialfolio_version`."""
    return tuple((name, _packaged(source, trialfolio_version)) for name, source in _FILES)


def _packaged(source: str, trialfolio_version: str) -> bytes:
    content = files("trialfolio").joinpath("init_data", source).read_bytes()
    if source == "README.md":
        content = content.replace(b"{version}", trialfolio_version.encode())
    return content
