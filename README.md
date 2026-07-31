# Pulse — Agentic PR Triage & Review

> **An intelligent overlay for open-source maintainers.** Pulse watches your GitHub pull requests, classifies them (human-vs-AI authorship, risk level, blast radius), and drafts triage reports that you approve before they ever post to your repo. No spam, no slop — just the maintainer's time back.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev)

---

## What Pulse Does

| Pain Point | How Pulse Solves It |
|---|---|
| Drowning in low-quality AI-generated PRs | Heuristic + LLM classifier flags `ai_slop` and surfaces it for human review |
| PRs touching auth/crypto/payment slipping through | High-risk pattern matcher forces `high_risk` classification on sensitive files |
| No visibility into downstream impact | tree-sitter property graph computes the **blast radius** — every caller affected by your change |
| Maintainer time wasted on trivial PRs | Auto-categorizes `trivial` PRs (typos, deps) and short-circuits the review |
| Reviewer assignment is guesswork | Suggested reviewer area + suggested labels per triage report |
| Agents posting on your behalf without consent | **Human-in-the-loop**: every report requires explicit `Approve & Post` in the dashboard |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    PULSE DASHBOARD (React 19 + Vite)      │
│  ┌────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │ PR Queue   │  │ Triage      │  │ Blast Radius      │  │
│  │ (incoming) │  │ Report View │  │ Graph (D3/React   │  │
│  │            │  │ (approve/   │  │ Flow)             │  │
│  │            │  │ reject)     │  │                   │  │
│  └────────────┘  └─────────────┘  └───────────────────┘  │
│                                                          │
│  WebSocket <── Real-time agent progress updates          │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP + WebSocket
┌──────────────────────┴───────────────────────────────────┐
│              FASTAPI BACKEND (Python 3.12)                │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │         PR TRIAGE AGENT (LangGraph 1.2.9)         │    │
│  │  Classify → Blast Radius → Report → [HUMAN] → Post│    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │         SEMANTIC KNOWLEDGE ENGINE                  │    │
│  │  tree-sitter (parse) + LanceDB (vectors) +         │    │
│  │  PropertyGraph (callers/blast radius)              │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │         GITHUB INTEGRATION LAYER                   │    │
│  │  Webhook receiver + REST client + OAuth flow      │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│              POSTGRESQL 16 + LANCEDB                      │
│  Repos, PRs, Triage Reports, Approvals  │  Code Vectors  │
└──────────────────────────────────────────────────────────┘
```

---

## Stack

| Layer | Technology | Version |
|---|---|---|
| Web framework | FastAPI | 0.141.1 |
| Agent orchestration | LangGraph | 1.2.9 |
| Parsing | tree-sitter | 0.26.0 |
| Vector database | LanceDB | 0.36.0 |
| Relational DB | PostgreSQL + SQLAlchemy 2.0 (async) | 16 / 2.0+ |
| LLM access | LiteLLM | latest |
| GitHub API | PyGithub | 2.9.1 |
| Frontend | React 19 + Vite + TypeScript | — |
| Styling | Tailwind CSS | 4 |
| Graph viz | D3.js + React Flow | — |
| Real-time | WebSocket (FastAPI native) | — |
| Containerization | Docker Compose | — |

---

## Directory Structure

```
pulse/
├── docker-compose.yml
├── .env.example
├── README.md
├── LICENSE
│
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial.py
│   │
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── repo.py
│       │   └── user.py
│       │
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── pr.py
│       │   ├── triage.py
│       │   └── repo.py
│       │
│       ├── github/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── webhooks.py
│       │   └── oauth.py
│       │
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── parser.py
│       │   ├── indexer.py
│       │   ├── graph.py
│       │   └── queries.py
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── triage.py
│       │   ├── prompts.py
│       │   └── classifier.py
│       │
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── dashboard.py
│       │   └── ws.py
│       │
│       └── services/
│           ├── __init__.py
│           ├── triage_service.py
│           └── index_service.py
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   ├── Dockerfile
│   ├── nginx.conf
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   └── PRDetail.tsx
│       ├── components/
│       │   ├── PRQueue.tsx
│       │   ├── TriageReport.tsx
│       │   ├── BlastRadiusGraph.tsx
│       │   ├── ApprovalPanel.tsx
│       │   ├── RepoSelector.tsx
│       │   └── Header.tsx
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   └── useTriage.ts
│       └── types/
│           └── index.ts
│
└── scripts/
    ├── init_db.sh
    └── seed_data.py
```

---

## Quickstart (Docker Compose)

### Prerequisites

- Docker + Docker Compose
- A GitHub account with a repository to test against
- An LLM API key (Anthropic Claude recommended; OpenAI or local Ollama also work)
- A Voyage AI or OpenAI API key for embeddings

### 1. Clone and configure

```bash
git clone https://github.com/rawdripcollective-codec/pulse.git
cd pulse

cp .env.example .env
# Edit .env with your API keys
```

### 2. Start the application

```bash
docker compose up --build
```

This launches four services:

| Service | Port | URL |
|---|---|---|
| PostgreSQL | 5432 | (internal) |
| Redis | 6379 | (internal) |
| Backend API | 8000 | http://localhost:8000/docs |
| Frontend dashboard | 5173 | http://localhost:5173 |

### 3. Connect a repository

Open http://localhost:5173 in your browser.

1. Click **Add Repository** and authenticate via GitHub OAuth
2. Select a repository to monitor
3. Pulse clones the repo locally and builds the semantic index (1–5 minutes)
4. Once indexed, the PR queue populates as new PRs are opened

### 4. Test with a PR

1. Open a pull request in your connected repository
2. Pulse receives the webhook and starts triage automatically
3. Within 30–60 seconds, a triage report appears under **Awaiting Approval**
4. Review the classification, blast radius visualization, and suggested action
5. Click **Approve & Post to GitHub** to publish the comment — or **Reject** to skip

---

## Triage Pipeline

Every PR flows through this 5-stage LangGraph state machine:

```
┌──────────┐   ┌────────────┐   ┌──────────┐   ┌────────┐   ┌──────┐
│ Classify │ → │ Blast      │ → │ Generate │ → │ Wait   │ → │ Post │
│ PR       │   │ Radius     │   │ Report   │   │ Human  │   │ to   │
│          │   │            │   │          │   │ (HITL) │   │ GH    │
└──────────┘   └────────────┘   └──────────┘   └────────┘   └──────┘
```

1. **Classify** — heuristic AI-marker scan + LLM verdict → `human_first | ai_assisted | ai_slop | trivial | high_risk`
2. **Blast Radius** — for each changed file, walk the property graph to find every downstream caller
3. **Generate Report** — LLM synthesizes a one-paragraph summary, key findings, suggested action, and labels
4. **Human Approval** — graph pauses (`interrupt_before=["action"]`); the report sits in the dashboard waiting for `Approve` or `Reject`
5. **Post to GitHub** — only on explicit approval: comment posted, labels applied

---

## Configuration Reference

All settings live in `backend/app/config.py` and can be overridden via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic`, `openai`, or `ollama` |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Main reasoning model |
| `LLM_API_KEY` | — | Required for Anthropic or OpenAI |
| `LLM_BASE_URL` | — | For Ollama: `http://localhost:11434/v1` |
| `EMBEDDING_MODEL` | `voyage-code-2` | Vector embedding model |
| `EMBEDDING_API_KEY` | — | Required for embeddings |
| `EMBEDDING_DIMENSIONS` | `1536` | Vector size (must match model) |
| `GITHUB_CLIENT_ID` | — | From GitHub OAuth App |
| `GITHUB_CLIENT_SECRET` | — | From GitHub OAuth App |
| `GITHUB_WEBHOOK_SECRET` | — | Random string for HMAC verification |
| `DATABASE_URL` | `postgresql+asyncpg://pulse:pulse@localhost:5432/pulse` | Async SQLAlchemy URL |
| `REDIS_URL` | `redis://localhost:6379/0` | For WebSocket pub/sub |
| `SECRET_KEY` | (change me) | JWT signing key |

---

## Development

### Run backend locally (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start Postgres + Redis separately, then:
uvicorn app.main:app --reload --port 8000
```

### Run frontend locally

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Linting & types

```bash
cd backend && ruff check . && mypy app/
cd frontend && npm run lint && npm run build
```

---

## What's Out of Scope (Phase 2+)

This MVP focuses on PR triage. Future phases add:

- Voice input / TTS output (multimodal input pipeline is built but not wired)
- Figma/screenshot → issue spec generation
- Cross-repo intelligence aggregation
- Auto-bounty system / contribution economy
- Yjs/CRDT real-time collaboration
- Federated Git protocol support

The `SemanticIndexer`, `PropertyGraph`, and `TriageService` are all built with extension points for these capabilities.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push to the branch
5. Open a Pull Request — and watch Pulse triage it 😄

---

## License

MIT © Pulse Contributors
