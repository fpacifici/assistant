# Assistant Development Guide for AI Agents

Assistant is a smart shared note taking system. It is meant to allow
people to organize their knowledge in notes and notebooks like Evernote.
It also includes an AI agent to search, manage and summarize the knowledge
in a semantic way.

# Working with This Codebase

The repo structure is in [`Project Structure`](docs/project_structure.md)

## Project Overview

**Project Name**: assistant
**Type**: Python package
**Layout**: src layout with the package at `src/assistant/`
**Python Version**: >= 3.13
**Package Manager**: uv

## Architecture

Before making plans read the architecture documents:

Overall architecture: [`Architecture`](docs/architecture/README.md)

When working on the backend:

- Note service: the backend [`Notes Service`](docs/architecture/notesservice.md)
- The [`API`](docs/architecture/api.md)

When working on the frontend:

- Support for notes format: [`Markdown support`](docs/architecture/markdown.md)
- Frontend architecture: [`Web frontend`](docs/architecture/frontend.md)


## Quick Start

> [!NOTE]
> All development operations have to be done inside a virtual environment
> See the instructions below to know how to setup the venv

### Setup Development Environment

Use the makefile to manage the dev environment and the services.
Only if something does not work read [`devenv.md`](docs/devenv.md) for
the manual operations

#### Start dev services

We have a docker compose bundle for the db and other dev services

```bash
# Starts all the background services
make services-up

# Stops them
make services-down
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

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
pytest --cov=assistant --cov-report=term-missing
```

### Code Quality Checks

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

## Development Workflow

Every time you apply a change, run the relevant checks before committing.

**Backend changes** (anything under `src/` or `tests/`):

```bash
make check   # runs typecheck + lint + test
```

**Frontend changes** (anything under `frontend/`):

```bash
make frontend-check   # runs lint
make frontend-test    # runs vitest
```

### Writing Tests

#### Python tests

- Place tests in `tests/` mirroring the `src/assistant/` structure
- Use `test_` prefix for test files and functions
- Write tests as **module-level functions**, not methods inside classes
- Group related tests with comment separators (e.g. `# --- Create node ---`)
- Aim for high coverage but focus on meaningful tests
- Mock external dependencies

#### Frontend tests

- Place tests next to source files as `*.test.tsx` or in `frontend/src/test/`
- Use Vitest with React Testing Library
- Run with `make frontend-test` or `cd frontend && npm test`

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

### Start the application

The Makefile contains some targets to start and stop both frontend and api

```bash
# Start both frontend and backend
make dev

# Stop both
make dev-stop

# Start the backend API only
make server

# Start the frontend only
make frontend-dev
```

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
make server
```

The server runs on `http://localhost:8000` by default. Options:
- `--host` (default: 0.0.0.0)
- `--port` (default: 8000)
- `--reload` (auto-reload on code changes)

OpenAPI docs are available at `http://localhost:8000/docs`.

### Frontend

In order to start, lint and test the frontend alone

```bash
# Install frontend dependencies
make frontend-install

# Start frontend dev server
make frontend-dev

# Build frontend for production
make frontend-build

# Lint frontend code
make frontend-lint

# Run frontend tests (vitest)
make frontend-test

# Run all frontend checks (lint + test)
make frontend-check
```

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

**Python**: add the package to `pyproject.toml` under `[project.dependencies]`
(or `[project.optional-dependencies.dev]` for dev deps), then sync:

```bash
make sync   # runs uv sync --all-extras
```

**Frontend**: use npm from the `frontend/` directory:

```bash
cd frontend && npm install <package>
```

### Running Individual Tests

```bash
pytest tests/test_specific.py
pytest tests/test_specific.py::test_function_name
```

### Updating Documentation

1. Code-level: Update docstrings in the code
2. Architecture-level: Create or update ADRs in `docs/architecture/`
4. Project-level: Update README.md

## Conventions

### API Layer

API route handlers must not mutate ORM entities directly. All data
operations (create, read, update, delete) go through service functions in
`src/assistant/notes/service.py` or `src/assistant/notes/user_service.py`.
The service layer owns flush/transaction semantics; the API layer owns
HTTP concerns (request parsing, response serialization, session commit).
