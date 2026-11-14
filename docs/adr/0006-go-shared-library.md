# ADR-0006: Go code runs in-process as a C shared library

## Status
Accepted. Supersedes [ADR-0005](0005-rust-python-extension.md).

## Context
ADR-0005 put backend code in Rust, as a PyO3 extension. We have since decided
to write that code in Go instead. The constraints are unchanged: the API stays
in FastAPI, there is one deployable API image, and the expected uses are
library-like functions rather than services.

## Decision
- Build `go/` with `-buildmode=c-shared` into `libassistant_go.so`, and load it
  from `assistant.golib` with `ctypes`. Remove the Rust crate.
- Keep the logic in packages free of cgo, with the exports in `go/bindings`.
- Use one calling convention for every export (length-prefixed strings in, a
  malloc'd buffer and a status out, freed by `AssistantFree`), so Python needs
  one marshalling helper.
- Recover panics in the export wrapper and report them as errors.
- Build the library with `make go-build`, not as part of `uv sync`.

See [`docs/architecture/go.md`](../architecture/go.md) for the details.

## Consequences
- Calling Go is still a function call: no network and no second process.
- `ctypes` needs no build backend and no Python dependency, and `uv sync` no
  longer needs a compiler. Building the library now needs Go and a C compiler,
  locally, in CI and in the image.
- Marshalling, memory ownership and panic handling are hand-written, which is
  what ADR-0005 rejected this option for. One convention and one helper keep
  that layer small, but each new argument shape needs its own.
- A panic on a goroutine other than the caller's kills the API process.
- The `ctypes` signatures can drift from the exports; only tests that call the
  real library catch it.
- The Go runtime is not fork-safe, so the library loads lazily.

## Alternatives Considered
- **Keep Rust.** Safer bindings, but we prefer to write and maintain Go.
- **A Go service called over HTTP or gRPC.** Isolates crashes and scales
  independently, at the cost of a second deployable and a network hop. Worth
  revisiting for long-running or crash-prone work; the logic packages could move
  behind a server unchanged.
- **cffi or a generated binding (gopy).** cffi adds a dependency for little
  over `ctypes` at this size; gopy generates a CPython extension per Python
  version and adds a build step we do not need yet.

## References
- [cgo: exporting Go functions](https://pkg.go.dev/cmd/cgo#hdr-C_references_to_Go)
- [Go build modes](https://pkg.go.dev/cmd/go#hdr-Build_modes)
- [ctypes](https://docs.python.org/3/library/ctypes.html)
