"""Backend code written in Go, called in-process through a C shared library.

Each function here wraps one export of `go/bindings`. The calls block their
thread with the GIL released, so call them from `def` route handlers or
through `run_in_threadpool`. See `docs/architecture/go.md`.
"""

from __future__ import annotations

from assistant.golib._library import GoLibraryError, call_string

__all__ = ["GoLibraryError", "greet"]


def greet(name: str) -> str:
    """Build a greeting in Go.

    Raises:
        GoLibraryError: If `name` is empty.
    """
    return call_string("AssistantGreet", name)
