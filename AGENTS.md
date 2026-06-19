# Assistant Development Guide for AI Agents

... docs ...

## Project Structure

```
assistant/
├── src/
│   └── assistant/              # Main package
│       ├── adapters/           # Data source adapters & plugin system
│       │   └── plugins/        # Adapter plugins (e.g. fake for testing)
│       ├── agents/             # RAG agent, vector search, infra
│       ├── api/                # FastAPI REST API
│       │   ├── routes/         # Route handlers (users, notebooks, notes)
│       │   └── schemas/        # Pydantic request/response schemas
│       ├── cli/                # CLI entry points (server, client, db tools, chat)
│       ├── data/               # Static data assets
│       │   └── documents/
│       ├── evals/              # Evaluation framework
│       ├── models/             # SQLAlchemy ORM models & DB schema
│       ├── notes/              # Notes service layer (CRUD, positions, users)
│       └── tui/                # Terminal UI (Textual chat app)
├── tests/                      # Test suite (mirrors src/ structure)
├── docs/                       # Documentation
│   ├── architecture/           # System architecture
│   ├── adr/                    # Architecture Decision Records
│   └── modules/                # Module documentation
├── .claude/                    # Claude AI configuration
├── .cursorrules                # Cursor AI configuration
├── docker-compose.yml          # Dev services (Postgres)
├── Makefile                    # Build & dev commands
├── pyproject.toml              # Project configuration
└── README.md
```

# Working with This Codebase

## Project Overview

**Project Name**: assistant
**Type**: Python package
**Layout**: src layout with the package at `src/assistant/`
**Python Version**: >= 3.13
**Package Manager**: uv

## Architecture

The architecture of the system is described in [`Architecture`](docs/architecture/README.md)

## Quick Start

> [!NOTE]
> All development operations have to be done inside a virtual environment
> See the instructions below to know how to setup the venv

### Setup Development Environment

#### Start dev services

We have a docker compose bundle for the db and other dev services

```bash
# Start the devservices and detach
docker compose up -d

# Stops the devservices
docker compose down
```

#### Quick Setup (Recommended)

```bash
# Install uv if not already installed
make install-uv

# Set up everything
make dev-setup

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

#### Manual Setup

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

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
pytest --cov=assistant --cov-report=term-missing
```

### Code Quality Checks

#### Using Makefile (Recommended)

```bash
# Run all checks
make check

# Individual checks
make typecheck
make lint
make test

# Format code
make format

# Run pre-commit hooks
make pre-commit-run
```

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

## Development Workflow

Every time you apply a change, run tests and typechecking as described below.

### Writing Tests

- Place tests in `tests/` mirroring the `src/assistant/` structure
- Use `test_` prefix for test files and functions
- Write tests as **module-level functions**, not methods inside classes
- Group related tests with comment separators (e.g. `# --- Create node ---`)
- Aim for high coverage but focus on meaningful tests
- Mock external dependencies

### Type Checking

This project uses strict typing:
- All functions must have complete type hints
- Use `typing` module for complex types
- Avoid `Any` unless absolutely necessary
- Use `TYPE_CHECKING` for avoiding circular imports

### Documentation Standards

- Public APIs must have docstrings (Google style preferred)
- Complex logic should have explanatory comments
- Update module documentation when changing behavior
- Keep examples in sync with code

## Common Tasks

### Chat TUI

To run the interactive chat TUI that sends queries to the RAG agent and streams responses:

```bash
python -m assistant.cli.chat <thread_id>
```

Exit with **Ctrl+Q**. See [`docs/modules/tui.md`](docs/modules/tui.md) for details.

### REST API Server

Start the API server (requires Postgres to be running, see below):

```bash
# Set up the database (first time only)
python -m assistant.cli.setup_database

# Start the server
python -m assistant.cli.api_server
```

The server runs on `http://localhost:8000` by default. Options:
- `--host` (default: 0.0.0.0)
- `--port` (default: 8000)
- `--reload` (auto-reload on code changes)

OpenAPI docs are available at `http://localhost:8000/docs`.

### API Client CLI

A CLI client for manually calling the API:

```bash
# User operations
python -m assistant.cli.api_client create-user --email user@example.com --firstname Jane --lastname Doe
python -m assistant.cli.api_client get-user <uid>
python -m assistant.cli.api_client update-user <uid> --firstname Updated

# Notebook operations (--user-id required for create and list)
python -m assistant.cli.api_client create-notebook --name "My Notebook" --user-id <uid>
python -m assistant.cli.api_client list-notebooks --user-id <uid>
python -m assistant.cli.api_client get-notebook <notebook_id>
python -m assistant.cli.api_client delete-notebook <notebook_id>

# Note operations
python -m assistant.cli.api_client create-note --notebook-id <id> --title "My Note" --user-id <uid>
python -m assistant.cli.api_client list-notes --notebook-id <id>
python -m assistant.cli.api_client get-note --notebook-id <id> --note-id <id>
python -m assistant.cli.api_client delete-note --notebook-id <id> --note-id <id>
```

Options: `--base-url` (default: http://localhost:8000), `--offset`, `--limit` for list commands.

### Development services (Postgres)

When a task needs the Postgres database (e.g. running app code or tests that hit the DB), first ensure services are up by running `make services-up`. This is idempotent (no-op if the stack is already running). To stop the bundle when no longer needed, run `make services-down`.

### Adding a Dependency

```bash
# Add to pyproject.toml under [project.dependencies]
# or for dev dependencies under [project.optional-dependencies.dev]

# Then sync the environment
uv pip install -e ".[dev]"
```

### Running Individual Tests

```bash
pytest tests/test_specific.py
pytest tests/test_specific.py::test_function_name
```

### Updating Documentation

1. Code-level: Update docstrings in the code
2. Module-level: Update docs in `docs/modules/`
3. Architecture-level: Create or update ADRs in `docs/adr/`
4. Project-level: Update README.md

## Conventions

### API Layer

API route handlers must not mutate ORM entities directly. All data
operations (create, read, update, delete) go through service functions in
`src/assistant/notes/service.py` or `src/assistant/notes/user_service.py`.
The service layer owns flush/transaction semantics; the API layer owns
HTTP concerns (request parsing, response serialization, session commit).
