# Build the Rust extension as a wheel, so the final image carries no toolchain.
# Bookworm's glibc must not be newer than the one in the Python image below, or
# the extension will not load there. Keep in sync with rust/rust-toolchain.toml.
FROM rust:1.95-bookworm AS rust-builder

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/

WORKDIR /build
COPY rust ./rust
RUN uv build --wheel --python 3.13 --out-dir /wheels rust

FROM python:3.13-slim AS base

# Install uv (single static binary, no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first so this layer is cached across source-only changes
COPY pyproject.toml uv.lock ./
COPY rust/pyproject.toml ./rust/
RUN uv sync --frozen --no-install-project --no-install-package assistant-rust --no-dev

# Now copy the source and install the project itself
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini config.yaml README.md LICENSE ./
RUN uv sync --frozen --no-install-package assistant-rust --no-dev

# Install the extension built above
RUN --mount=type=bind,from=rust-builder,source=/wheels,target=/wheels \
    uv pip install --no-deps /wheels/*.whl

# Run as a non-root user
RUN groupadd --system assistant \
    && useradd --system --gid assistant --no-create-home assistant \
    && mkdir -p /app/data \
    && chown -R assistant:assistant /app/data
USER assistant

ENV PATH="/app/.venv/bin:${PATH}"

# Fail the build if the Rust extension cannot be loaded and called
RUN python -c "from assistant_rust import greet; print(greet('image build'))"

EXPOSE 8000

CMD ["python", "-m", "assistant.cli.api_server"]
