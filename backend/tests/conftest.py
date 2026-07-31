"""Shared pytest fixtures for the Pulse test suite.

Strategy:
- Database: use SQLite in-memory with aiosqlite for unit/integration tests
  (avoids the cost of a real Postgres in CI). Production uses asyncpg, but
  the ORM-level behavior is identical for our purposes.
- Embeddings: a fake embedder that returns deterministic zero vectors. The
  semantic search code path will return arbitrary results, but the index
  construction and storage logic is fully exercised.
- LLM: a stub `acompletion` that returns canned JSON.
- GitHub API: a stub `Github` client that returns canned PR/repo data.
- Time: freeze `datetime.now` where needed via freezegun (optional).
"""

import asyncio
import os
import sys
import threading
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure the backend root is on sys.path so `import app.*` works
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Override environment BEFORE importing any app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("EMBEDDING_API_KEY", "test-key")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "8")  # small for fast tests
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("DEBUG", "true")


# ─── Event loop (one per session for async tests) ─────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─── Database fixtures ────────────────────────────────────────

@pytest_asyncio.fixture
async def async_engine():
    """A fresh in-memory SQLite engine per test, with all tables created."""
    # Import models so they register on Base.metadata
    import app.models.repo  # noqa: F401
    import app.models.user  # noqa: F401
    from app.database import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncIterator[AsyncSession]:
    """An AsyncSession bound to the in-memory engine. Commits are no-ops."""
    factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def sample_repo(db_session: AsyncSession):
    """Insert a sample Repository row and return it."""
    from app.models.repo import Repository, RepoStatus

    repo = Repository(
        id=uuid.uuid4(),
        github_id=12345,
        full_name="acme/widget",
        owner="acme",
        name="widget",
        description="Sample repo for tests",
        default_branch="main",
        language="python",
        stars=42,
        status=RepoStatus.READY,
        indexed_at=datetime.now(UTC),
    )
    db_session.add(repo)
    await db_session.flush()
    return repo


@pytest_asyncio.fixture
async def sample_pr(db_session: AsyncSession, sample_repo):
    """Insert a sample PullRequest row tied to sample_repo."""
    from app.models.repo import (
        PRClassification,
        PullRequest,
        TriageStatus,
    )

    pr = PullRequest(
        id=uuid.uuid4(),
        repository_id=sample_repo.id,
        github_pr_id=99,
        number=7,
        title="Add retry logic",
        body="This PR adds exponential backoff to the webhook handler.",
        author="alice",
        author_avatar="https://avatars.githubusercontent.com/u/1?v=4",
        base_branch="main",
        head_branch="feature/retry",
        state="open",
        files_changed=2,
        additions=50,
        deletions=10,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        classification=PRClassification.HUMAN_FIRST,
        classification_confidence=0.91,
        triage_status=TriageStatus.AWAITING_APPROVAL,
    )
    db_session.add(pr)
    await db_session.flush()
    return pr


# ─── GitHub API mocks ─────────────────────────────────────────

class FakeGitHubClient:
    """Drop-in stand-in for `app.github.client.GitHubClient`.

    Returns canned PR / repo data so the triage pipeline can run end-to-end
    without hitting the real GitHub API.
    """

    def __init__(self, repo_full_name: str = "acme/widget", pr_number: int = 7):
        self.repo_full_name = repo_full_name
        self.pr_number = pr_number
        self.commented: list[tuple[str, int, str]] = []
        self.labeled: list[tuple[str, int, list[str]]] = []

    def get_repo(self, full_name: str):
        repo = MagicMock()
        repo.id = 12345
        repo.owner.login = "acme"
        repo.name = "widget"
        repo.description = "Sample repo"
        repo.default_branch = "main"
        repo.language = "python"
        repo.stargazers_count = 42
        repo.full_name = full_name
        repo.clone_url = "https://github.com/acme/widget.git"
        return repo

    def get_pr(self, full_name: str, pr_number: int):
        pr = MagicMock()
        pr.id = 99
        pr.number = pr_number
        pr.title = "Add retry logic"
        pr.body = "Exponential backoff for webhooks."
        pr.user.login = "alice"
        pr.user.avatar_url = "https://avatars.githubusercontent.com/u/1"
        pr.base.ref = "main"
        pr.head.ref = "feature/retry"
        pr.state = "open"
        pr.changed_files = 2
        pr.additions = 50
        pr.deletions = 10
        pr.created_at = datetime.now(UTC)
        pr.updated_at = datetime.now(UTC)
        pr.diff_url = "https://github.com/acme/widget/pull/7.diff"
        return pr

    def get_pr_files(self, full_name: str, pr_number: int):
        f1 = MagicMock()
        f1.filename = "app/webhooks.py"
        f2 = MagicMock()
        f2.filename = "tests/test_webhooks.py"
        return [f1, f2]

    def get_pr_diff(self, full_name: str, pr_number: int) -> str:
        return (
            "diff --git a/app/webhooks.py b/app/webhooks.py\n"
            "@@ -1,3 +1,10 @@\n"
            "+import time\n"
            "+\n"
            "+def retry(fn, max_attempts=3):\n"
            "+    for i in range(max_attempts):\n"
            "+        try:\n"
            "+            return fn()\n"
            "+        except Exception:\n"
            "+            time.sleep(2 ** i)\n"
        )

    def post_pr_comment(self, full_name: str, pr_number: int, body: str) -> None:
        self.commented.append((full_name, pr_number, body))

    def add_labels(
        self, full_name: str, pr_number: int, labels: list[str]
    ) -> None:
        self.labeled.append((full_name, pr_number, list(labels)))


@pytest.fixture
def fake_github():
    """A FakeGitHubClient instance for use in tests."""
    return FakeGitHubClient()


# ─── LLM mocks ────────────────────────────────────────────────

class FakeLLMResponse:
    def __init__(self, content: str):
        self.choices = [MagicMock()]
        self.choices[0].message.content = content


@pytest.fixture
def fake_llm_classifier_response():
    """A canned LLM classification response for `classify_pr`."""
    return {
        "classification": "human_first",
        "confidence": 0.92,
        "rationale": "Clean, well-documented change with clear test coverage.",
    }


@pytest.fixture
def fake_llm_report_response():
    """A canned LLM report-generation response for `report_generation_node`."""
    return """# Triage Report: Add retry logic

**One-line summary:** Adds exponential backoff to the webhook handler.

**Risk assessment:** Low — well-scoped, well-tested, no security impact.

**Key findings:**
- Clean separation of concerns
- Tests cover the new retry path
- No breaking changes to public API

**Suggested action:** approve

**Recommended reviewer:** Backend platform

**Suggested labels:** `enhancement`, `ready-to-merge`
"""


# ─── LanceDB stub ──────────────────────────────────────────────

class FakeLanceTable:
    """Drop-in for the lancedb table used in SemanticIndexer.

    Stores records in memory, supports the subset of operations we use.
    """

    def __init__(self):
        self.records: list[dict] = []

    def add(self, records: list[dict]) -> None:
        self.records.extend(records)

    def search(self, vector, query_type=None):
        return _FakeSearch(self.records, vector)

    def create_index(self, **kwargs) -> None:
        # No-op for tests
        pass

    def to_pandas(self):
        import pandas as pd
        return pd.DataFrame(self.records)


class _FakeSearch:
    def __init__(self, records: list[dict], vector):
        self.records = records
        self.vector = vector

    def limit(self, n: int):
        self._limit = n
        return self

    def to_list(self) -> list[dict]:
        return self.records[: self._limit]

    def where(self, condition: str):
        # Not used in current code path; return self for chaining safety
        return self


# ─── Generic helpers ──────────────────────────────────────────

@pytest.fixture
def sample_python_source() -> str:
    """A small Python module to exercise the tree-sitter parser."""
    return '''"""Sample module for parser tests."""

import os
from pathlib import Path


class Widget:
    """A widget."""

    def __init__(self, name: str):
        self.name = name

    def render(self) -> str:
        return f"<widget>{self.name}</widget>"


def make_widget(name: str) -> Widget:
    """Factory function."""
    return Widget(name)


def helper(x: int) -> int:
    """Calls render — a sibling function."""
    return make_widget(str(x)).render()
'''


@pytest.fixture
def sample_diff_text() -> str:
    return (
        "diff --git a/auth/login.py b/auth/login.py\n"
        "@@ -10,3 +10,8 @@\n"
        "+def authenticate(user, password):\n"
        "+    if not user:\n"
        "+        raise ValueError('no user')\n"
        "+    return check_password(user, password)\n"
    )


# ─── HTTP client fixture for route tests ──────────────────────

# httpx + asgi-lifespan let us exercise the FastAPI app in-process without
# binding to a real port. We override the `get_db` dependency so route
# handlers see the test session, not the production async_session_factory.

import httpx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport


@pytest_asyncio.fixture
async def api_client(async_engine, db_session):
    """An httpx AsyncClient wired to the FastAPI app with the test DB.

    Usage:
        async def test_something(api_client, sample_repo):
            resp = await api_client.get("/api/repos")
            assert resp.status_code == 200
            data = resp.json()
            ...

    The fixture:
    - Imports the FastAPI app (lazy import to avoid pulling in DB at module
      load time before our env vars are set)
    - Overrides `get_db` to yield the in-memory test session
    - Drives the FastAPI lifespan (startup/shutdown)
    - Returns a configured httpx.AsyncClient
    - Cleans up the dependency override on teardown
    """
    from app.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with LifespanManager(app), httpx.AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ─── Postgres guard ───────────────────────────────────────────

def _is_postgres_url(url: str | None) -> bool:
    """True if the given URL points at Postgres (not SQLite)."""
    if not url:
        return False
    return url.startswith(("postgresql", "postgres"))


@pytest.fixture(scope="session")
def postgres_required():
    """Skip a test if the session DATABASE_URL is not Postgres.

    Use as a fixture dependency:
        def test_postgres_specific_thing(postgres_required):
            ...
    """
    if not _is_postgres_url(os.environ.get("DATABASE_URL")):
        pytest.skip(
            "Postgres-only test — set DATABASE_URL to a postgres:// URL "
            "to enable (e.g. via 'make test-pg')"
        )


@pytest.fixture(scope="session")
def sqlite_required():
    """Skip a test if the session DATABASE_URL is not SQLite.

    Used for tests that exercise SQLite-specific behavior (e.g. JSON
    fallback to plain JSON).
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("sqlite"):
        pytest.skip("SQLite-only test")


# ─── Embedded Postgres (for `make test-pg` and CI service) ─────

# When the user runs `make test-pg` (or CI starts the postgres service),
# the DATABASE_URL points at a real Postgres. But for the conftest to
# work even on a developer machine without Docker, we can boot an embedded
# Postgres via `pgserver` (a small standalone server bundled with
# PostgreSQL binaries). This makes the tests fully self-contained.

def _start_embedded_postgres_if_needed() -> None:
    """Boot an embedded Postgres if DATABASE_URL is unset or empty.

    The embedded server is process-wide (started once for the test session).
    Tests that need real Postgres should depend on the `postgres_url`
    fixture, which sets DATABASE_URL to the embedded server's URI.
    """
    global _embedded_pg_server
    if _embedded_pg_server is not None:
        return
    if os.environ.get("DATABASE_URL", "").startswith(("postgresql", "postgres")):
        return  # already configured externally
    try:
        import tempfile

        import pgserver
    except ImportError:
        return  # pgserver not installed; tests will skip

    with _embedded_pg_lock:
        if _embedded_pg_server is not None:
            return
        pgdata = tempfile.mkdtemp(prefix="pulse-pg-")
        server = pgserver.get_server(pgdata)
        server.cleanup()
        server.ensure_pgdata_inited()
        server.ensure_postgres_running()
        uri = server.get_uri()
        # Convert to asyncpg URL
        asyncpg_uri = uri.replace("postgresql://", "postgresql+asyncpg://", 1)
        os.environ["DATABASE_URL"] = asyncpg_uri
        os.environ["DATABASE_URL_SYNC"] = uri
        _embedded_pg_server = server
        print(f"\n[pulse-tests] Started embedded Postgres at {asyncpg_uri}")


_embedded_pg_server = None
_embedded_pg_lock = threading.Lock()


@pytest.fixture(scope="session")
def postgres_url():
    """Get a Postgres URL, starting an embedded server if needed.

    Use as a dependency on any test that requires real Postgres:

        def test_jsonb_query(postgres_url):
            # ...
    """
    _start_embedded_postgres_if_needed()
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgresql", "postgres")):
        pytest.skip(
            "Postgres-only test — set DATABASE_URL=postgresql+asyncpg://... "
            "or run `make test-pg` to start an embedded server."
        )
    return url
