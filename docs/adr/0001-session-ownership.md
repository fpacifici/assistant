# ADR-0001: Session ownership and dependency injection

## Status
Accepted

## Context
Several modules need to interact with the database using SQLAlchemy `Session` objects.
If modules create their own sessions implicitly, it becomes difficult to:

- Control transaction boundaries
- Ensure consistent reads/writes across related operations
- Write deterministic tests
- Reason about resource ownership and lifetime

## Decision
Database sessions are **owned by the caller** and must be passed explicitly to any function/method
that performs database operations.

Concretely:

- Code that needs DB access must accept a `Session` parameter (no internal `get_session_factory()`,
  no implicit session creation).
- Components like the provider `Registry` may *use* a `Session`, but must not *create* one.
- Higher-level orchestration code (e.g. jobs/CLI entrypoints) is responsible for creating and
  scoping sessions via `get_session_factory()` and `with session_factory() as session:`.

## Consequences
- **Pros**:
  - Transaction boundaries are explicit and testable.
  - Callers can coordinate multiple operations within the same session.
  - Easier to inject test sessions and mock behaviors.
- **Cons**:
  - More parameters to thread through call stacks.
  - Some convenience wrappers may be needed for ergonomics (but they should live in orchestration
    layers, not in low-level components).

## Alternatives Considered
- **Implicit session creation inside helpers**:
  - Rejected because it obscures ownership, encourages nested sessions, and complicates tests.

## References
- PR review discussion in `fpacifici/assistant` PR #3
