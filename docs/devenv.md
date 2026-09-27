# Manual dev end setup

> [!NOTE]
> Under normal operations you should not read this. The dev env standard
> operations are done via `make` as described in [`AGENTS.md`](../AGENTS.md)

## Manual setup of the virtual env

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in development mode with dev dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Code quality checks

#### Manual Commands

```bash
# Type checking
mypy src/

# Linting and formatting
ruff check src/
black --check src/

# Auto-fix issues
ruff check --fix src/
black src/
```

## Enabling Sentry locally

Sentry is off by default. To send local errors, traces and replays to Sentry
(see [`observability.md`](architecture/observability.md)):

```bash
# .env (repo root) — backend
SENTRY_DSN=https://<key>@<org>.ingest.us.sentry.io/<backend-project>
SENTRY_ENVIRONMENT=development

# frontend/.env.local — frontend (read by Vite at startup/build)
VITE_SENTRY_DSN=https://<key>@<org>.ingest.us.sentry.io/<frontend-project>
```

Restart `make dev` after changing them. Tests always run with Sentry off.
