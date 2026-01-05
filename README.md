# Assistant

An AI agent that organizes your knowledge from multiple sources and summarizes topics.

Assistant reads your notes from the sources you configure, it ingests your
knowledge base from different sources, it processes and it generates summaries
of topics you ask for.

It is also able to keep track of a list of blogs and feeds you configure and
include them in the summary as sources.

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
