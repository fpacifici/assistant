FROM python:3.13-slim AS base

# Install uv (single static binary, no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first so this layer is cached across source-only changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the source and install the project itself
COPY src ./src
COPY README.md LICENSE ./
RUN uv sync --frozen --no-dev

# Run as a non-root user
RUN groupadd --system assistant \
    && useradd --system --gid assistant --no-create-home assistant \
    && mkdir -p /app/data \
    && chown -R assistant:assistant /app/data
USER assistant

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["python", "-m", "assistant.cli.api_server"]
