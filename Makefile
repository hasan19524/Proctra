# Procto — canonical task entry points (CI / Linux / macOS).
# On Windows, use the equivalent PowerShell scripts in ./scripts (see DEVELOPMENT.md).

SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help setup dev dev-backend dev-frontend dev-full infra-up infra-down \
        db-upgrade db-revision test lint typecheck check fmt

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend + frontend dependencies and run migrations
	cd backend && uv sync
	cd frontend && npm install
	cp -n .env.example .env || true
	cd backend && uv run alembic upgrade head

infra-up: ## Start infrastructure containers (postgres, redis, livekit)
	docker compose up -d

infra-down: ## Stop infrastructure containers (keeps volumes)
	docker compose stop

db-upgrade: ## Apply Alembic migrations
	cd backend && uv run alembic upgrade head

db-revision: ## Create a migration: make db-revision m="message"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

dev: ## Run backend (8001) and frontend (3001) with hot reload
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Run FastAPI only
	cd backend && uv run uvicorn app.main:app --reload --port 8001

dev-frontend: ## Run Next.js only
	cd frontend && npm run dev

dev-full: ## Everything (including apps) in Docker — uncomment the app services first
	docker compose --profile full up --build

test: ## Backend + frontend tests
	cd backend && uv run pytest
	cd frontend && npm run test

lint: ## Backend + frontend linting
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run format:check

typecheck: ## Backend + frontend type checking
	cd backend && uv run mypy app tests
	cd frontend && npm run typecheck

check: lint typecheck test ## lint + typecheck + tests

fmt: ## Auto-fix formatting on both sides
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format
