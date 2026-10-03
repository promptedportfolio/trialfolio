"""A real pseudo-terminal in the test process, for prompts and typed answers (release 0.1.0,
test pairing: the terminal). It isn't a double: `stdin` and `stderr` are its terminal side, so
`isatty()` is true because they are terminals.

R01-T15's terminal support runs a command in a subprocess under a pseudo-terminal; this one
serves code called in the test process. POSIX only: Windows has no pseudo-terminals. The module
still imports there, so a test module that uses it collects, and only its terminal tests skip.
"""

import os
import threading
from types import TracebackType
from typing import Self, TextIO


class PseudoTerminal:
    """A pseudo-terminal. What the code writes is collected from the other side by a thread, so
    a long display never fills the terminal's buffer, and `press` sends keys as a user would."""

    def __init__(self) -> None:
        self._controller, terminal = os.openpty()
        self.stdin: TextIO = open(os.dup(terminal), encoding="utf-8")  # noqa: SIM115
        self.stderr: TextIO = open(terminal, "w", encoding="utf-8")  # noqa: SIM115
        self._shown = bytearray()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self._closed = False

    def _read(self) -> None:
        while True:
            try:
                data = os.read(self._controller, 4096)
            except OSError:  # Linux reports EIO once the terminal side is closed
                return
            if not data:
                return
            self._shown += data

    def press(self, keys: str | bytes) -> None:
        """Sends keys, as typed: text in UTF-8, or bytes as they are. A line takes effect at
        `\\n`, and `\\x04` at the start of a line is the end of input."""
        os.write(self._controller, keys.encode() if isinstance(keys, str) else keys)

    def shown(self) -> str:
        """Closes the terminal side, and returns everything shown on it, typed echo included,
        with the terminal's `\\r\\n` line endings read as `\\n`, and bytes that aren't UTF-8
        replaced."""
        if not self._closed:
            self._closed = True
            # Imported here, because Windows has no termios (see the module's docstring).
            import termios

            # Waits until the reader has taken everything written, before closing.
            termios.tcdrain(self.stderr.fileno())
            self.stdin.close()
            self.stderr.close()
            self._reader.join(timeout=10)
            os.close(self._controller)
        return self._shown.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shown()
