"""Loading of the Go shared library and its calling convention.

The library is built from `go/bindings` with `make go-build` into this
directory. Every exported function except `AssistantFree` takes its string
arguments as a pointer and a byte length, writes a malloc'd buffer and its
length to two out-parameters, and returns 0 on success or 1 on error (the
buffer then holds the error message). The caller frees the buffer with
`AssistantFree`. See `go/bindings/main.go`.
"""

from __future__ import annotations

import ctypes
from functools import cache
from pathlib import Path

LIBRARY_PATH = Path(__file__).with_name("libassistant_go.so")

_SUCCESS = 0

# Exports that follow the one-string calling convention. Add new ones here.
_STRING_FUNCTIONS = ("AssistantGreet",)


class GoLibraryError(ValueError):
    """An error returned by a function of the Go library."""


@cache
def _load() -> ctypes.CDLL:
    """Load the library on first use, after any fork of the process.

    The Go runtime starts threads when the library loads, and threads do not
    survive a `fork`, so loading at import time would break forked workers.
    `CDLL` releases the GIL for the duration of each call.
    """
    if not LIBRARY_PATH.exists():
        msg = f"Go library not found at {LIBRARY_PATH}: run `make go-build`"
        raise RuntimeError(msg)
    library = ctypes.CDLL(str(LIBRARY_PATH))
    library.AssistantFree.argtypes = [ctypes.c_void_p]
    library.AssistantFree.restype = None
    for name in _STRING_FUNCTIONS:
        function = getattr(library, name)
        function.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        function.restype = ctypes.c_int
    return library


def call_string(name: str, argument: str) -> str:
    """Call the exported Go function `name` with one string, returning a string.

    Raises:
        GoLibraryError: If the Go function returns an error or panics.
    """
    library = _load()
    if name not in _STRING_FUNCTIONS:
        msg = f"{name} is not declared in _STRING_FUNCTIONS"
        raise RuntimeError(msg)
    function = getattr(library, name)
    encoded = argument.encode()
    buffer = ctypes.c_void_p()
    length = ctypes.c_size_t()
    status = function(encoded, len(encoded), ctypes.byref(buffer), ctypes.byref(length))
    try:
        value = (
            ctypes.string_at(buffer.value, length.value).decode()
            if buffer.value and length.value
            else ""
        )
    finally:
        library.AssistantFree(buffer)
    if status != _SUCCESS:
        raise GoLibraryError(value)
    return value
