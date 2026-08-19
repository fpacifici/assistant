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
