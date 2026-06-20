# Assistant

A note-taking system with an AI agent that organizes your knowledge.

Assistant is a note-taking application that helps you capture, store, and
organize your notes. It includes an AI agent that can process your knowledge
base from multiple sources, generate summaries of topics you ask for, and
keep track of blogs and feeds you configure to include as sources.

## Overview

...


## Installation

### Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

#### Quick Setup with Makefile

```bash
# Install uv (if not already installed)
make install-uv

# Set up everything (virtual environment + dependencies + pre-commit)
make dev-setup

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

## Development

### Makefile Commands

```bash
# See all available commands
make help

# Run tests
make test

# Run type checker
make typecheck

# Run linter
make lint

# Format code
make format

# Run all checks (typecheck + lint + test)
make check

# Install pre-commit hooks
make pre-commit-install

# Run pre-commit on all files
make pre-commit-run
```

## Frontend

The web UI is a React app in the `frontend/` directory.

### Setup

```bash
# Install dependencies
make frontend-install

# Start the dev server (requires the API server running)
make frontend-dev

# Or start both backend and frontend together
make dev
```

The frontend dev server runs at `http://localhost:5173` and expects the
API server at `http://localhost:8000`. Make sure Postgres is running
(`make services-up`) and you have at least one user in the database.

### Build

```bash
make frontend-build    # Production build
make frontend-lint     # Lint
make frontend-check    # All frontend checks
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **For Developers**: Start with `docs/agents/working-with-this-codebase.md`
- **For Architecture**: See `docs/architecture/README.md`
- **For AI Agents**: See `docs/agents/README.md`
- **For Decisions**: See `docs/adr/README.md`


## Contributing

1. Read the documentation in `docs/agents/`
2. Follow the coding conventions in `docs/agents/coding-conventions.md`
3. Write tests for new functionality
4. Update documentation as needed
5. Create an ADR for significant decisions

## License

See [LICENSE](LICENSE) for details.
