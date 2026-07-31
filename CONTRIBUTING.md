# Contributing to Pulse

Thanks for your interest in Pulse — an agentic PR triage platform. This guide
will help you get set up, make a focused change, and submit a pull request
that we can review quickly.

## Code of conduct

Be kind. Be direct. We follow the standard
[Contributor Covenant](https://www.contributor-covenant.org/).

## Project layout

```
pulse/
├── backend/          # FastAPI + LangGraph + tree-sitter + LanceDB
│   ├── app/
│   │   ├── agents/   # PR Triage Agent (LangGraph state machine)
│   │   ├── engine/   # Semantic knowledge engine (parser, graph, indexer)
│   │   ├── github/   # GitHub client + OAuth + webhooks + App auth
│   │   ├── models/   # SQLAlchemy ORM models
│   │   ├── routes/   # FastAPI HTTP + WebSocket routes
│   │   ├── schemas/  # Pydantic DTOs
│   │   └── services/ # Business logic (triage orchestration, indexing)
│   ├── tests/        # pytest suite — see below
│   └── pyproject.toml
├── frontend/         # React 19 + Vite + TypeScript + Tailwind 4
├── envs/             # Per-provider .env templates (Anthropic, OpenAI, Ollama, GitHub App)
├── scripts/          # dev tooling (merge_env.py, init_db.sh, seed_data.py)
└── Makefile          # `make ollama`, `make up`, `make test`, etc.
```

## Getting set up

### Prerequisites
- Python 3.12+
- Node.js 22+
- Docker + Docker Compose (for the full stack)
- An LLM API key (Anthropic, OpenAI, or local Ollama)

### One-time setup
```bash
# Clone the repo
git clone https://github.com/rawdripcollective-codec/pulse.git
cd pulse

# Install backend + frontend deps
make install

# Generate a .env from your preferred provider preset
make ollama           # local Ollama (no key needed)
# OR
make anthropic        # Anthropic Claude
# OR
make openai           # OpenAI

# Edit .env to fill in any real keys (e.g. LLM_API_KEY, GITHUB_TOKEN)

# Start the full stack
make up
```

The dashboard runs at http://localhost:5173 and the API at http://localhost:8000.

## Development workflow

Pulse follows **Test-Driven Development (TDD)**. The workflow is:

1. **Write the failing test first.** Find the right test file under
   `backend/tests/` (or create one), write a test that exercises the
   behavior you want to add.
2. **Run the test and watch it fail.** `cd backend && pytest tests/path/to/test.py -v`
3. **Write the minimal implementation** that makes the test pass.
4. **Re-run the test and watch it pass.**
5. **Refactor** while keeping the test green.
6. **Commit** with a conventional commit message (see below).

### Running tests

```bash
make test           # full suite
make test-cov       # with coverage report
cd backend && pytest tests/unit/test_parser.py -v   # single file
cd backend && pytest -k test_approve -v            # by name pattern
```

### Running the linter

```bash
make lint
```

We use **ruff** for Python and **eslint** for TypeScript. CI runs both — fix
any lint errors before opening a PR.

## Commit message format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

<optional body — explain the why, not the what>

<optional footer — e.g. "Refs: #123" or "BREAKING CHANGE: ...">
```

**Types:**
- `feat`: new user-facing feature
- `fix`: bug fix
- `refactor`: code change that neither fixes a bug nor adds a feature
- `test`: add or fix tests
- `docs`: documentation only
- `chore`: tooling, dependencies, build config
- `perf`: performance improvement

**Examples:**
```
feat(agents): add severity scoring to deep review prompt
fix(triage): mark report posted_to_github on successful comment
refactor(engine): expose high_centrality_nodes as public API
test(backend): add integration tests for the approve flow
```

## Pull request guidelines

1. **One logical change per PR.** If your fix involves refactoring + new
   feature, split it into two PRs.
2. **Add tests.** Any new behavior needs test coverage. Any bug fix needs
   a regression test.
3. **Update the README** if you change user-facing behavior (new env var,
   new endpoint, new UI element).
4. **Run `make test && make lint` locally** before pushing.
5. **Reference the issue** in the PR description (e.g. "Fixes #42").
6. **Wait for CI to pass.** Our pipeline runs pytest + ruff + mypy + a
   frontend build.

## Code style

- **Python:** We use ruff with the default rules. Line length 100.
  Type hints on every public function. Docstrings on every public class
  and non-trivial function.
- **TypeScript:** Strict mode (already configured in `tsconfig.json`).
  Prefer named exports. Co-locate types with the code that uses them.
- **Naming:** snake_case for Python, camelCase for TypeScript.
- **Imports:** Group by stdlib → third-party → local, separated by blank
  lines. Sort alphabetically within each group.

## Adding a new language to the tree-sitter parser

1. `pip install tree-sitter-<lang>`
2. Add a `LANGUAGE_FACTORIES` entry in `app/engine/parser.py` with a
   factory function (NOT a `Language` instance — see the comment there
   for why).
3. Add the extension to `EXTENSION_TO_LANG`.
4. Add unit tests in `tests/unit/test_parser.py::TestParserMultipleLanguages`.

## Adding a new LLM provider

1. Add a preset file in `envs/<provider>.env.example`.
2. Update the table in `README.md` under "Provider Setup".
3. The provider is auto-detected by `settings.llm_provider` and routed
   through LiteLLM — no code changes needed for cloud providers.
4. For non-LiteLLM providers, add a custom client in
   `app/services/triage_service.py` and wire it into the agent.

## Reporting security issues

Please **do not** file public GitHub issues for security bugs. Email
security concerns to the maintainers directly (see the repo's
SECURITY.md, when present) and we'll respond within 48 hours.

## License

By contributing to Pulse, you agree that your contributions will be
licensed under the MIT License. See [LICENSE](LICENSE).
