"""JSON nested too deeply for the decoder, and a thread to decode it on, so the decoder raises
`RecursionError` on every machine.

Python 3.12 counts the decoder's nested calls, but Python 3.14 measures the stack they use. On
the main thread, that stack's size is the platform's limit, such as `ulimit -s`, and where it's
large enough, as on GitHub's Ubuntu runner, Python 3.14 decodes all 100,000 levels. A thread's
stack has the size the test sets. At 4 MiB, Python 3.14 raises `RecursionError` before the levels
fit, and Python 3.12 reaches its count before the stack runs out: at 1 MiB, Python 3.12 crashed,
on Linux and macOS.
"""

import threading
from collections.abc import Callable
from typing import Final

DEEP: Final = b"[" * 100_000 + b"]" * 100_000
"""Valid JSON, nested 100,000 levels deep."""

STACK_SIZE: Final = 4 << 20
"""The thread's stack, 4 MiB."""


def on_a_fixed_stack[T](call: Callable[[], T]) -> T:
    """Returns what `call` returns, or raises what it raises, running it on a thread whose stack
    is `STACK_SIZE`."""
    returned: list[T] = []
    raised: list[BaseException] = []

    def run() -> None:
        try:
            returned.append(call())
        except BaseException as error:  # noqa: BLE001 - raised again on the calling thread.
            raised.append(error)

    previous = threading.stack_size(STACK_SIZE)
    try:
        thread = threading.Thread(target=run)
        thread.start()
    finally:
        threading.stack_size(previous)
    thread.join()
    if raised:
        raise raised[0]
    return returned[0]
