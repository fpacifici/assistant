# Build the Go shared library, so the final image carries no toolchain. cgo links
# it against glibc, so bookworm's glibc must not be newer than the one in the
# Python image below, or the library will not load there. Keep the Go version in
# sync with go/go.mod.
FROM golang:1.26-bookworm AS go-builder

WORKDIR /build/go
COPY go/go.mod ./
RUN go mod download
COPY go ./
RUN CGO_ENABLED=1 go build -trimpath -buildmode=c-shared \
    -o /out/libassistant_go.so ./bindings

FROM python:3.13-slim AS base

# Install uv (single static binary, no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first so this layer is cached across source-only changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the source and install the project itself
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini config.yaml README.md LICENSE ./
RUN uv sync --frozen --no-dev

# Install the Go library built above next to its Python wrapper
COPY --from=go-builder /out/libassistant_go.so ./src/assistant/golib/

# Run as a non-root user
RUN groupadd --system assistant \
    && useradd --system --gid assistant --no-create-home assistant \
    && mkdir -p /app/data \
    && chown -R assistant:assistant /app/data
USER assistant

ENV PATH="/app/.venv/bin:${PATH}"

# Fail the build if the Go library cannot be loaded and called
RUN python -c "from assistant.golib import greet; print(greet('image build'))"

EXPOSE 8000

CMD ["python", "-m", "assistant.cli.api_server"]
