.DEFAULT_GOAL := help

# ── Configuration ──────────────────────────────────────────────────────────
PYTHON      := python3.12
UV          := uv
APP_MODULE  := app.main:app
HOST        := 0.0.0.0
PORT        := 8000
DOCKER_IMAGE ?= dlp-archive

# ── Virtual environment ────────────────────────────────────────────────────
VENV := .venv
BIN  := $(VENV)/bin

# ── Help (self-documenting) ────────────────────────────────────────────────
## Show this help message
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Environment setup ──────────────────────────────────────────────────────
## Create the virtual environment and install all dependencies
install: ## Create the virtual environment and install all dependencies
	$(UV) sync --frozen

## Install only production dependencies (no dev tools)
install-prod: ## Install only production dependencies (no dev tools)
	$(UV) sync --frozen --no-dev

## Update all dependencies from pyproject.toml
update: ## Update all dependencies from pyproject.toml
	$(UV) lock --upgrade
	$(UV) sync

# ── Development server ────────────────────────────────────────────────────
## Run the FastAPI dev server with auto-reload
dev: ## Run the FastAPI dev server with auto-reload
	$(UV) run uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

## Run the production server (no auto-reload)
run: ## Run the production server (no auto-reload)
	$(UV) run uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT)

# ── Linting & formatting ──────────────────────────────────────────────────
## Check code with ruff (lint + format check)
lint: ## Check code with ruff (lint + format check)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

## Auto-fix lint issues and format code
format: ## Auto-fix lint issues and format code
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

# ── Testing ────────────────────────────────────────────────────────────────
## Run the full test suite
test: ## Run the full test suite
	$(UV) run pytest tests/ -v

## Run tests with coverage report
test-cov: ## Run tests with coverage report
	$(UV) run pytest tests/ -v --cov=app --cov-report=term-missing

## Run a single test file (usage: make test-one FILE=test_health)
test-one: ## Run a single test file (usage: make test-one FILE=test_health)
	$(UV) run pytest tests/$(FILE).py -v

# ── Docker ─────────────────────────────────────────────────────────────────
## Build the Docker image
docker-build: ## Build the Docker image
	docker build -t $(DOCKER_IMAGE) .

## Run the Docker container locally
docker-run: ## Run the Docker container locally
	docker run --rm -p $(PORT):$(PORT) -v /config:/config $(DOCKER_IMAGE)

# ── Housekeeping ───────────────────────────────────────────────────────────
## Remove caches, bytecode, and the virtual environment
clean: ## Remove caches, bytecode, and the virtual environment
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache

.PHONY: help install install-prod update dev run lint format test test-cov test-one docker-build docker-run clean
