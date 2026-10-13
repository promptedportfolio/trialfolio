"""Where the file system puts a path: the path an existing one resolves to, and whether one path is
in a directory.

`existing_path` resolves a path the user gave as opening it would, for a run that
`trialfolio report` reads, or that a review configuration names. `is_within` tells whether a
path is in a directory, for `trialfolio init`'s workspace, which its log file stays out of.
"""

import os
from pathlib import Path
from unicodedata import normalize


def existing_path(path: str | os.PathLike[str]) -> str | None:
    """`path` where the file system resolves it, or None when nothing exists there. A `..` after
    a symbolic link leads to the parent of the link's target, as opening the path does, not where
    `os.path.abspath` would lead, by removing it with the segment before it."""
    try:
        # Whether anything exists there, as opening the path finds it. realpath alone can't tell:
        # Python 3.12's removes a `..` after a file, which the file system refuses.
        os.stat(path)
        return os.path.realpath(path, strict=True)
    except (OSError, ValueError):
        # Nothing exists there: a link leads to nothing, a part can't be read or is a file, or the
        # path holds a NUL, which no path can.
        return None


def is_within(path: Path, directory: Path) -> bool:
    """Whether `path` is `directory` or in it, where the file system puts each: `directory` as
    the output directory's claim reads a path, with `..` resolved as written, and `path` as
    creating it does, once symbolic links are resolved.

    The parts of each that exist are compared as the file system identifies them, so another
    spelling of the same folder counts: in another case, on a file system that ignores case, as
    macOS's and Windows' do by default, or in another Unicode normalization, on one that ignores
    that, as macOS's does. Names that don't exist yet are compared ignoring both, as such a file
    system would: on one that doesn't ignore them, a path that differs from the directory only
    that way counts as in it too."""
    outer = _existing(os.path.abspath(directory))
    inner = _existing(os.path.realpath(path))
    if outer is None or inner is None:
        return False  # Where no part of a path exists, nothing can be created.
    _, status, unmade = outer
    start, start_status, names = inner
    if unmade:
        # The directory doesn't exist yet: `path` is in it only if it will be made in the same
        # folder, through the same names.
        same_names = _folded(names[: len(unmade)]) == _folded(unmade)
        return same_names and os.path.samestat(start_status, status)
    return any(_is(part, status) for part in (start, *start.parents))


def _existing(path: str) -> tuple[Path, os.stat_result, tuple[str, ...]] | None:
    """`path`'s deepest part that exists, its status, and the names after it; None when no part
    of it exists."""
    whole = Path(path)
    for part in (whole, *whole.parents):
        try:
            status = os.stat(part)
        except OSError:
            continue
        return part, status, whole.parts[len(part.parts) :]
    return None


def _is(path: Path, status: os.stat_result) -> bool:
    """Whether `path` exists, and is the file `status` describes."""
    try:
        return os.path.samestat(os.stat(path), status)
    except OSError:
        return False


def _folded(names: tuple[str, ...]) -> tuple[str, ...]:
    """The names as a file system that ignores case and Unicode normalization compares them:
    Unicode's canonical caseless match."""
    return tuple(normalize("NFD", normalize("NFD", name).casefold()) for name in names)
