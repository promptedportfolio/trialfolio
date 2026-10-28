"""What a directory holds, so a test can show that a command left it as it was.

TS-T03 moved them here from the interface's conftest.
"""

from pathlib import Path


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file and directory under `root`, hidden ones included: a file's bytes, or None for a
    directory."""
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


type Entry = tuple[bool, int, int, bytes | None]


def metadata(root: Path) -> dict[str, Entry]:
    """The root and everything under it, hidden entries included: whether each is a directory,
    and its size, modification time, and bytes."""
    entries: dict[str, Entry] = {}
    for path in (root, *sorted(root.rglob("*"))):
        status = path.stat()
        directory = path.is_dir()
        entries[path.relative_to(root).as_posix()] = (
            directory,
            status.st_size,
            status.st_mtime_ns,
            None if directory else path.read_bytes(),
        )
    return entries
