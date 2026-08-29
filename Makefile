.PHONY: help install-uv setup sync install test typecheck lint format check clean pre-commit-install pre-commit-run services-up services-down server docker-build docker-server frontend-install frontend-dev frontend-build frontend-lint frontend-test frontend-check docker-build-frontend docker-frontend dev dev-stop

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
	@echo "  make format              - Format code with ruff"
	@echo "  make check               - Run all checks (typecheck, lint, test)"
	@echo "  make pre-commit-install  - Install pre-commit hooks"
	@echo "  make pre-commit-run      - Run pre-commit on all files"
	@echo "  make services-up         - Ensure Docker Compose services (e.g. Postgres) are running; no-op if already up"
	@echo "  make services-down      - Stop and remove Docker Compose services (Postgres)"
	@echo "  make server              - Start the FastAPI API server"
	@echo "  make docker-build        - Build the API server Docker image"
	@echo "  make docker-server       - Start the FastAPI API server in Docker"
	@echo "  make docker-build-frontend - Build the nginx-fronted frontend Docker image"
	@echo "  make docker-frontend     - Run the frontend image against the dockerized API server"
	@echo "  make frontend-install    - Install frontend dependencies"
	@echo "  make frontend-dev        - Start frontend dev server"
	@echo "  make frontend-build      - Build frontend for production"
	@echo "  make frontend-lint       - Lint frontend code"
	@echo "  make frontend-test       - Run frontend tests (vitest)"
	@echo "  make frontend-check      - Run all frontend checks"
	@echo "  make dev                 - Start both backend and frontend dev servers"
	@echo "  make dev-stop            - Stop backend and frontend dev servers"
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
	pytest tests

# Run type checker
typecheck:
	@echo "Running type checker..."
	mypy src/

# Run linter
lint:
	@echo "Running linter..."
	@ruff check src/ tests/

# Format code
format:
	@echo "Formatting code..."
	@ruff check --fix src/ tests/
	@ruff format src/ tests/
	@echo "✅ Code formatted"

# Run all checks
check: typecheck lint test
	@echo "✅ All checks passed"

# Install pre-commit hooks (uses project .venv)
pre-commit-install:
	@echo "Installing pre-commit hooks..."
	@uv pip install pre-commit
	@.venv/bin/pre-commit install
	@echo "✅ Pre-commit hooks installed"

# Run pre-commit on all files (uses project .venv)
pre-commit-run:
	@echo "Running pre-commit on all files..."
	@.venv/bin/pre-commit run --all-files

# Ensure Docker Compose services (e.g. Postgres) are running; no-op if already up
services-up:
	@if docker compose ps --status running -q 2>/dev/null | grep -q .; then \
		echo "Docker Compose services already running"; \
	else \
		docker compose up -d; \
	fi

# Stop and remove Docker Compose services (Postgres)
services-down:
	@docker compose down

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

# Start the FastAPI API server
server:
	@echo "Starting API server on http://localhost:8000 ..."
	@.venv/bin/python -m assistant.cli.api_server

# Build the API server Docker image
docker-build:
	@echo "Building assistant-api Docker image..."
	@docker build -f docker/backend/Dockerfile -t assistant-api .
	@echo "✅ Docker image built"

# Start the FastAPI API server in Docker (requires services-up for Postgres)
docker-server: docker-build services-up
	@echo "Starting API server in Docker on http://localhost:8000 ..."
	@docker network create assistant-net >/dev/null 2>&1 || true
	@docker run --rm -it \
		--name assistant-api \
		--network assistant-net \
		-p 8000:8000 \
		--add-host=host.docker.internal:host-gateway \
		--env-file .env \
		-e DATABASE_URL=postgresql://$${POSTGRES_USER:-assistant}:$${POSTGRES_PASSWORD:-assistant}@host.docker.internal:$${POSTGRES_PORT:-5432}/$${POSTGRES_DB:-assistant} \
		assistant-api

# Build the nginx-fronted frontend Docker image
docker-build-frontend:
	@echo "Building assistant-frontend Docker image..."
	@docker build -f docker/frontend/Dockerfile -t assistant-frontend .
	@echo "✅ Frontend Docker image built"

# Run the frontend image, proxying API calls to the dockerized backend.
# Requires `make docker-server` running in another shell (same assistant-net network).
docker-frontend: docker-build-frontend
	@echo "Starting frontend in Docker on http://localhost:8080 ..."
	@docker network create assistant-net >/dev/null 2>&1 || true
	@docker run --rm -it \
		--name assistant-frontend \
		--network assistant-net \
		-p 8080:80 \
		-e BACKEND_HOST=assistant-api \
		-e BACKEND_PORT=8000 \
		assistant-frontend

# Install frontend dependencies
frontend-install:
	@echo "Installing frontend dependencies..."
	@cd frontend && npm install
	@echo "✅ Frontend dependencies installed"

# Start frontend dev server
frontend-dev:
	@echo "Starting frontend dev server..."
	@cd frontend && npm run dev

# Build frontend for production
frontend-build:
	@echo "Building frontend..."
	@cd frontend && npm run build
	@echo "✅ Frontend built"

# Lint frontend code
frontend-lint:
	@echo "Linting frontend..."
	@cd frontend && npm run lint

# Run frontend tests
frontend-test:
	@echo "Running frontend tests..."
	@cd frontend && npm test

# Run all frontend checks
frontend-check: frontend-lint frontend-test
	@echo "✅ Frontend checks passed"

# Start both backend and frontend dev servers
dev:
	@echo "Starting backend and frontend..."
	@.venv/bin/python -m assistant.cli.api_server & cd frontend && npm run dev

# Stop backend and frontend dev servers
dev-stop:
	@echo "Stopping dev servers..."
	@lsof -ti:8000 | xargs kill 2>/dev/null || true
	@lsof -ti:5173 | xargs kill 2>/dev/null || true
	@echo "Dev servers stopped"

# Quick development setup (run once)
dev-setup: setup install pre-commit-install frontend-install
	@echo ""
	@echo "✅ Development environment ready!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Activate virtual environment: source .venv/bin/activate"
	@echo "  2. Start coding!"
	@echo "  3. Run 'make check' before committing"
