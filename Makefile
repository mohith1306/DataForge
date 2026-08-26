.PHONY: help install dev up down migrate seed test lint typecheck

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

dev: ## Start development servers
	docker compose up -d postgres clickhouse
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web: ## Start frontend dev server
	cd apps/web && npm run dev

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

migrate: ## Run database migrations
	cd apps/api && uv run alembic upgrade head

seed: ## Seed ClickHouse with demo data
	uv run python data/seed/seed_clickhouse.py

test: ## Run tests
	uv run pytest -v

lint: ## Run linter
	uv run ruff check .

typecheck: ## Run type checker
	uv run mypy .
