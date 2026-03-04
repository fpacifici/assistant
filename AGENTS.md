# Assistant Development Guide for AI Agents

... docs ...

## Project Structure

```
assistant/
├── src/
│   └── assistant/          # Main package
│       └── __init__.py
├── tests/                  # Test suite
├── docs/                   # Documentation
│   ├── architecture/       # System architecture
│   ├── adr/               # Architecture Decision Records
│   ├── modules/           # Module documentation
│   └── agents/            # AI agent guidelines
├── .cursorrules           # Cursor AI configuration
├── .claude/               # Claude AI configuration
├── pyproject.toml         # Project configuration
└── README.md              # This file
```

# Working with This Codebase

## Project Overview

**Project Name**: assistant
**Type**: Python package
**Layout**: src layout with the package at `src/assistant/`
**Python Version**: >= 3.13
**Package Manager**: uv

## Quick Start

> [!NOTE]
> All development operations have to be done inside a virtual environment
> See the instructions below to know how to setup the venv

### Setup Development Environment

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

### Adding New Modules

1. Create the module file in `src/assistant/`
2. Add type hints to all functions and classes
3. Create corresponding test file in `tests/`
4. Document the module in `docs/modules/`
5. Update `src/assistant/__init__.py` if exposing public API

### Making Architecture Decisions

1. Create a new ADR in `docs/adr/` following the template
2. Discuss the decision, alternatives, and consequences
3. Update the index in `docs/adr/README.md`
4. Implement the decision
5. Reference the ADR in relevant code comments

### Writing Tests

- Place tests in `tests/` mirroring the `src/assistant/` structure
- Use `test_` prefix for test files and functions
- Use `Test` prefix for test classes
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
