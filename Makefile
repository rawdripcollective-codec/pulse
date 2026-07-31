# Pulse — Makefile for common dev tasks

.PHONY: help install dev up down logs clean test lint build seed

help:
	@echo "Pulse — Agentic PR Triage"
	@echo ""
	@echo "Usage:"
	@echo "  make install    Install all dependencies (backend + frontend)"
	@echo "  make dev        Start backend + frontend in dev mode"
	@echo "  make up         Start full stack via docker compose"
	@echo "  make down       Stop docker compose stack"
	@echo "  make logs       Tail docker compose logs"
	@echo "  make test       Run backend tests"
	@echo "  make lint       Lint backend (ruff) and frontend (eslint)"
	@echo "  make build      Build production frontend bundle"
	@echo "  make seed       Seed the database with demo data"
	@echo "  make clean      Remove build artifacts and caches"

install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

dev:
	@echo "→ Start backend in one terminal: cd backend && uvicorn app.main:app --reload"
	@echo "→ Start frontend in another:    cd frontend && npm run dev"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && pytest

lint:
	cd backend && ruff check . && mypy app/
	cd frontend && npm run lint

build:
	cd frontend && npm run build

seed:
	cd backend && python -m scripts.seed_data

clean:
	rm -rf backend/.mypy_cache backend/.pytest_cache backend/.ruff_cache
	rm -rf frontend/dist frontend/node_modules
	rm -rf frontend/.vite
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
