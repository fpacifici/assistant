# ADR-0005: Rust code runs in-process as a Python extension

## Status
Superseded by [ADR-0006](0006-go-shared-library.md)

## Context
We want to write some backend code in Rust while keeping the API in FastAPI, so
a route handler needs a way to call a Rust module. There is one deployable API
image today, and the first uses are expected to be library-like functions
rather than services.

## Decision
- Make `rust/` a Python extension module, `assistant_rust`, built with PyO3 and
  maturin.
- Make it a uv workspace member and a dependency of `assistant`, so `uv sync`
  builds it and a clean checkout needs no extra step.
- Keep the logic in modules free of PyO3 types, with the bindings in `lib.rs`.
- Target the stable ABI, so one build covers every Python from 3.13 on.

See [`docs/architecture/rust.md`](../architecture/rust.md) for the details.

## Consequences
- Calling Rust is a function call: no network, no second process to deploy,
  monitor or version against the API. Arguments and errors map to Python types
  without a serialization layer.
- A panic on the calling thread fails the request instead of the server.
- Building now needs Rust, locally, in CI and in the image, and `uv sync` needs
  it even for work that never touches `rust/`.
- Rust runs inside the API process, so memory bugs in `unsafe` code or
  dependencies can still crash it, and CPU-heavy work competes with the API.
- The `.pyi` stub is maintained by hand and can drift from the bindings.

## Alternatives Considered
- **A Rust service called over HTTP or gRPC.** Better isolation and independent
  scaling, at the cost of a second deployable, a schema and a network hop on
  every call. Worth revisiting for long-running or crash-prone work; the logic
  modules could move behind a server without touching their code.
- **A C ABI loaded with `ctypes`.** Works without a build backend, but needs
  hand-written marshalling, manual memory management and panic handling, all of
  which PyO3 provides.
- **Go through `-buildmode=c-shared`.** Prototyped first. It works, but it needs
  that same hand-written layer, and a panic on a goroutine kills the server.

## References
- [PyO3 user guide](https://pyo3.rs)
- [maturin user guide](https://www.maturin.rs)
- [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/)
