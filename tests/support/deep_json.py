"""JSON nested too deeply for the decoder, and a thread to decode it on, so the decoder raises
`RecursionError` on every machine.

Python 3.12 counts the decoder's nested calls, but Python 3.14 measures the stack they use, so
how deep it decodes depends on the machine. On the main thread, the stack's size is the
platform's limit, such as `ulimit -s`. A thread's stack has the size the test sets. On GitHub's
Ubuntu runner, Python 3.14 decoded 100,000 levels on the main thread, and on a thread with a
4 MiB stack too. A million levels don't fit in 4 MiB at even 5 bytes a level, so Python 3.14
raises `RecursionError`. Python 3.12 reaches its count before the stack runs out: with a 1 MiB
stack, it crashed, on Linux and macOS.
"""

import threading
from collections.abc import Callable
from typing import Final

DEEP: Final = b"[" * 1_000_000 + b"]" * 1_000_000
"""Valid JSON, nested a million levels deep."""

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
