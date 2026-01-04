.PHONY: help install-uv setup sync install test typecheck lint format check clean pre-commit-install pre-commit-run

# Default target
help:
	@echo "Available targets:"
	@echo "  make install-uv          - Install uv package manager"
	@echo "  make setup               - Create virtual environment"
	@echo "  make sync                - Sync dependencies with uv"
	@echo "  make install             - Install package in development mode"
	@echo "  make test                - Run all tests"
	@echo "  make typecheck           - Run mypy type checker"
	@echo "  make lint                - Run ruff linter"
	@echo "  make format              - Format code with black and ruff"
	@echo "  make check               - Run all checks (typecheck, lint, test)"
	@echo "  make pre-commit-install  - Install pre-commit hooks"
	@echo "  make pre-commit-run      - Run pre-commit on all files"
	@echo "  make clean               - Remove generated files and cache"

# Install uv package manager
install-uv:
	@echo "Installing uv..."
	@curl -LsSf https://astral.sh/uv/install.sh | sh
	@echo "✅ uv installed successfully"

# Create virtual environment
setup:
	@echo "Creating virtual environment..."
	@uv venv
	@echo "✅ Virtual environment created"
	@echo "Activate it with: source .venv/bin/activate"

# Sync dependencies using uv
sync:
	@echo "Syncing dependencies..."
	@uv sync --all-extras
	@echo "✅ Dependencies synced"

# Install package in development mode
install:
	@echo "Installing package in development mode..."
	@uv pip install -e ".[dev]"
	@echo "✅ Package installed"

# Run all tests
test:
	@echo "Running tests..."
	@pytest

# Run type checker
typecheck:
	@echo "Running type checker..."
	@mypy src/

# Run linter
lint:
	@echo "Running linter..."
	@ruff check src/ tests/

# Format code
format:
	@echo "Formatting code..."
	@ruff check --fix src/ tests/
	@black src/ tests/
	@echo "✅ Code formatted"

# Run all checks
check: typecheck lint test
	@echo "✅ All checks passed"

# Install pre-commit hooks
pre-commit-install:
	@echo "Installing pre-commit hooks..."
	@uv pip install pre-commit
	@pre-commit install
	@echo "✅ Pre-commit hooks installed"

# Run pre-commit on all files
pre-commit-run:
	@echo "Running pre-commit on all files..."
	@pre-commit run --all-files

# Clean generated files and cache
clean:
	@echo "Cleaning up..."
	@rm -rf .venv/
	@rm -rf build/
	@rm -rf dist/
	@rm -rf *.egg-info/
	@rm -rf .pytest_cache/
	@rm -rf .mypy_cache/
	@rm -rf .ruff_cache/
	@rm -rf htmlcov/
	@rm -rf .coverage
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "✅ Cleanup complete"

# Quick development setup (run once)
dev-setup: setup install pre-commit-install
	@echo ""
	@echo "✅ Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Activate virtual environment: source .venv/bin/activate"
	@echo "  2. Start coding!"
	@echo "  3. Run 'make check' before committing"
