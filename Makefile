# Pulse — Makefile for common dev tasks

.PHONY: help install dev up down logs clean test test-pg test-cov lint build seed
.PHONY: ollama ollama-cloud anthropic openai env-from ollama-doctor

# Default provider target
PROVIDER ?= ollama

help:
	@echo "Pulse — Agentic PR Triage"
	@echo ""
	@echo "Core:"
	@echo "  make install    Install all dependencies (backend + frontend)"
	@echo "  make dev        Start backend + frontend in dev mode (no docker)"
	@echo "  make up         Start full stack via docker compose"
	@echo "  make down       Stop docker compose stack"
	@echo "  make logs       Tail docker compose logs"
	@echo "  make test       Run backend tests (SQLite)"
	@echo "  make test-pg    Run backend tests against real Postgres"
	@echo "  make test-cov   Run backend tests with coverage"
	@echo "  make lint       Lint backend (ruff) and frontend (eslint)"
	@echo "  make build      Build production frontend bundle"
	@echo "  make seed       Seed the database with demo data"
	@echo "  make clean      Remove build artifacts and caches"
	@echo ""
	@echo "LLM Provider shortcuts (generates .env from envs/<provider>.env.example):"
	@echo "  make ollama         Local Ollama (no API key needed)"
	@echo "  make ollama-cloud   Hosted Ollama (needs API key)"
	@echo "  make anthropic      Anthropic Claude (needs API key)"
	@echo "  make openai         OpenAI GPT (needs API key)"
	@echo "  make env-from PROVIDER=foo    Generate .env from a specific envs/foo.env.example"
	@echo ""
	@echo "Ollama helpers:"
	@echo "  make ollama-doctor  Check if Ollama is reachable and which models are pulled"

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

# Run the Postgres-only tests (tests/integration/test_postgres.py).
# Strategy: prefer an externally-set DATABASE_URL (e.g. from CI service
# container), otherwise boot an embedded Postgres via the `pgserver` package
# (the conftest auto-boots it when DATABASE_URL points at sqlite).
# Requires: pip install pgserver asyncpg (already in dev deps).
test-pg:
	cd backend && python -m pytest tests/integration/test_postgres.py -v --no-header

test-cov:
	cd backend && pytest --cov=app --cov-report=term-missing

lint:
	cd backend && ruff check . && mypy app/
	cd frontend && npm run lint

format:
	cd backend && ruff format .

build:
	cd frontend && npm run build

seed:
	cd backend && python -m scripts.seed_data

# ─── Provider shortcuts ───────────────────────────────────────
# Each target creates .env from the corresponding envs/<name>.env.example
# template. Run `make ollama` and then `make up` — that's the whole loop.

ollama:
	@$(MAKE) env-from PROVIDER=ollama-local
	@echo ""
	@echo "→ Make sure Ollama is running: 'ollama serve' (or it auto-runs on macOS)"
	@echo "→ Pull a model: 'ollama pull llama3.1 && ollama pull nomic-embed-text'"
	@echo "→ Now run: make up"

ollama-cloud:
	@$(MAKE) env-from PROVIDER=ollama-cloud
	@echo ""
	@echo "→ Edit .env and paste your Ollama Cloud API key in LLM_API_KEY and EMBEDDING_API_KEY"
	@echo "→ Now run: make up"

anthropic:
	@$(MAKE) env-from PROVIDER=anthropic
	@echo ""
	@echo "→ Edit .env and paste your Anthropic + Voyage API keys"
	@echo "→ Now run: make up"

openai:
	@$(MAKE) env-from PROVIDER=openai
	@echo ""
	@echo "→ Edit .env and paste your OpenAI API key"
	@echo "→ Now run: make up"

env-from:
	@if [ -z "$(PROVIDER)" ]; then \
		echo "✗ PROVIDER not set. Usage: make env-from PROVIDER=ollama-local"; \
		exit 1; \
	fi
	@if [ ! -f "envs/$(PROVIDER).env.example" ]; then \
		echo "✗ envs/$(PROVIDER).env.example not found"; \
		echo "  Available: $$(ls envs/*.env.example | xargs -n1 basename | sed 's/.env.example//' | tr '\n' ' ')"; \
		exit 1; \
	fi
	@if [ -f .env ]; then \
		echo "⚠  .env already exists — backing up to .env.bak"; \
		mv .env .env.bak; \
	fi
	@python3 scripts/merge_env.py .env.example envs/$(PROVIDER).env.example > .env
	@echo "✓ Created .env from .env.example + envs/$(PROVIDER).env.example"

ollama-doctor:
	@echo "→ Checking Ollama at http://localhost:11434 ..."
	@if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then \
		echo "✓ Ollama is running"; \
		echo ""; \
		echo "Installed models:"; \
		curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; models=json.load(sys.stdin).get('models',[]); print('\n'.join(f'  - {m[\"name\"]}' for m in models) or '  (none — pull one with: ollama pull llama3.1)')"; \
	else \
		echo "✗ Ollama is NOT reachable at http://localhost:11434"; \
		echo "  Install: https://ollama.com/download"; \
		echo "  Then run: ollama serve &"; \
		exit 1; \
	fi

clean:
	rm -rf backend/.mypy_cache backend/.pytest_cache backend/.ruff_cache
	rm -rf frontend/dist frontend/node_modules
	rm -rf frontend/.vite
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
