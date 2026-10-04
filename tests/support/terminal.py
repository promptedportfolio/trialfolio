"""The terminal: a real pseudo-terminal, for prompts, typed answers, and a real Ctrl-C (release
0.1.0, test pairing). It isn't a double: `isatty()` is true because the streams are terminals.

- **`Terminal`** runs a command in a new process under a pseudo-terminal: the installed command,
  or the test launcher's. The terminal is the process's controlling terminal, so Ctrl-C sends it a
  real SIGINT.
- **`PseudoTerminal`** serves code called in the test process, such as the CLI's entry function.
  R01-T14 created it; R01-T15 added `Terminal`.

POSIX only: Windows has no pseudo-terminals. The module still imports there, so a test module that
uses it collects, and only its terminal tests skip.
"""

import errno
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Final, Self, TextIO

CTRL_C: Final = b"\x03"
"""What Ctrl-C sends: the terminal's default interrupt character."""

_REVOKED: Final = frozenset({errno.EBADF, errno.ENOENT})
"""What waiting on a terminal that macOS has revoked gives: `EBADF`, or `ENOENT` when the tests run
in a macOS sandbox (`sandbox-exec`), as a coding agent's shell may."""

_CONTROLLING: Final = """
import fcntl
import os
import sys
import termios

# A new session's leader, as start_new_session made this process, takes the terminal as its
# controlling terminal, so the terminal sends its interrupt character as SIGINT to this process
# group. exec keeps the session, the descriptors, and the environment, the network guard's
# PYTHONPATH included.
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
os.execvp(sys.argv[1], sys.argv[1:])
"""


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


class Terminal:
    """Runs `command` in a new process, with stdin and stderr on a pseudo-terminal, which is its
    controlling terminal, and stdout on a pipe. What it shows on the terminal and writes to stdout
    is collected by threads, so neither fills up. `cwd` and `env` are as `subprocess` takes them;
    without `env` the process inherits the test's environment."""

    def __init__(
        self,
        command: Sequence[str | Path],
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._controller, self._terminal = os.openpty()
        self._shown = bytearray()
        self._lock = threading.Lock()
        try:
            self._process = subprocess.Popen(
                [sys.executable, "-c", _CONTROLLING, *(str(arg) for arg in command)],
                stdin=self._terminal,
                stdout=subprocess.PIPE,
                stderr=self._terminal,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except BaseException:
            os.close(self._terminal)
            os.close(self._controller)
            raise
        self._stdout = b""
        self._readers = [
            threading.Thread(target=self._read_terminal, daemon=True),
            threading.Thread(target=self._read_stdout, daemon=True),
        ]
        for reader in self._readers:
            reader.start()
        self._closed = False

    def _read_terminal(self) -> None:
        while True:
            try:
                data = os.read(self._controller, 4096)
            except OSError:  # Linux reports EIO once the terminal side is closed
                return
            if not data:
                return
            with self._lock:
                self._shown += data

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        self._stdout = self._process.stdout.read()

    def press(self, keys: str | bytes) -> None:
        """Sends keys, as typed: text in UTF-8, or bytes as they are. A line takes effect at
        `\\n`, `\\x04` at the start of a line is the end of input, and `CTRL_C` is Ctrl-C. Once
        the terminal is closed, because the process has ended, this fails the test."""
        assert not self._closed, f"the process has ended:\n{self._text()}"
        os.write(self._controller, keys.encode() if isinstance(keys, str) else keys)

    def wait_for(self, text: str, timeout: float = 30) -> None:
        """Waits until the terminal has shown `text`, such as a prompt, and fails the test if it
        doesn't within `timeout` seconds, or the process ends without showing it. A process that
        ended has its terminal closed, as `wait` does."""
        deadline = time.monotonic() + timeout
        while text not in self._text():
            ended = self._process.poll() is not None
            if ended:
                # It may have shown the text after the check above, just before it ended. This
                # takes everything it showed, as `wait` does, before deciding.
                self._close()
                if text in self._text():
                    return
            if ended or time.monotonic() > deadline:
                raise AssertionError(f"the terminal never showed {text!r}:\n{self._text()}")
            time.sleep(0.01)

    def wait(self, timeout: float = 60) -> int:
        """Waits for the process to end, and returns its exit code: negative for a signal."""
        code = self._process.wait(timeout)
        self._close()
        return code

    def shown(self) -> str:
        """Everything shown on the terminal so far, typed echo included, with its `\\r\\n` line
        endings read as `\\n`, and bytes that aren't UTF-8 replaced."""
        return self._text()

    @property
    def stdout(self) -> str:
        """Everything the process wrote to stdout, once it has ended."""
        assert self._closed, "stdout is complete only once the process has ended"
        return self._stdout.decode("utf-8", errors="replace")

    def _text(self) -> str:
        with self._lock:
            shown = bytes(self._shown)
        return shown.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Imported here, because Windows has no termios (see the module's docstring).
        import termios

        # The test's side of the terminal stayed open, so nothing the process wrote was lost. This
        # waits until the reader has taken it all, then closes, even if the wait fails. macOS, as
        # BSD does, revokes a controlling terminal when its session's leader, the process, ends,
        # once its output has drained; the descriptor is then no longer valid.
        try:
            termios.tcdrain(self._terminal)
        except termios.error as error:
            if error.args[0] not in _REVOKED:
                raise
        finally:
            os.close(self._terminal)
            for reader in self._readers:
                reader.join(timeout=10)
            os.close(self._controller)
            assert self._process.stdout is not None
            self._process.stdout.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._process.poll() is None:
            self._process.kill()
        self.wait()
