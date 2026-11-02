"""Type stubs of the Rust extension. Keep in sync with `src/lib.rs`."""

def greet(name: str) -> str:
    """Build a greeting.

    Raises:
        ValueError: If `name` is empty.
    """
