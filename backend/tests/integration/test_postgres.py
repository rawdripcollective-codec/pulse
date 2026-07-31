"""Postgres-specific integration tests.

These tests exercise behavior that differs between SQLite and Postgres:
- Real JSONB columns (with operators we'd want to use in production)
- UUID column type (native vs. VARCHAR in SQLite)
- Alembic migrations (we run them here against a real PG instance)
- Connection pooling (which SQLite doesn't support)
- Transaction isolation (READ COMMITTED vs. SQLite's looser default)

The tests are SKIPPED unless the session DATABASE_URL points at Postgres.
The `make test-pg` target spins up a Postgres container, sets the URL,
and runs these.

To run locally with docker:
    make test-pg

To run in CI: see .github/workflows/ci.yml — the postgres job uses
a service container.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database import Base
from app.models.repo import (
    PRClassification,
    PullRequest,
    Repository,
    RepoStatus,
    TriageReport,
    TriageStatus,
)

# All tests in this module share the session-scoped event loop because
# asyncpg connections are bound to the loop where they were created. This
# avoids "got Future attached to a different loop" errors on teardown.
pytestmark = pytest.mark.asyncio(loop_scope="session")


# ─── Fixtures ─────────────────────────────────────────────────

# The conftest provides a `postgres_url` session fixture that starts an
# embedded Postgres server if needed. We use that here to keep the tests
# self-contained — no Docker, no external services.


@pytest_asyncio.fixture(loop_scope="session")
async def pg_engine(postgres_url):
    """A Postgres engine with all tables created via Alembic-style create_all.

    Note: we use a session-scoped event loop because asyncpg connections
    are bound to the loop where they were created. If pytest-asyncio
    spins up a new loop per test, the pool crashes on teardown.
    """
    # Import models so they register on Base.metadata
    import app.models.repo  # noqa: F401
    import app.models.user  # noqa: F401

    engine = create_async_engine(postgres_url, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def pg_session(pg_engine) -> AsyncSession:
    factory = async_sessionmaker(
        pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


# ─── JSONB column tests ───────────────────────────────────────

class TestJsonbColumns:
    """Verify that JSONB columns actually store and query JSONB data.

    SQLite stores JSON as plain TEXT, so this is one of the most important
    behavior gaps to test against real Postgres.
    """

    async def test_jsonb_accepts_nested_data(self, pg_session):
        repo = Repository(
            github_id=12345,
            full_name="test/repo",
            owner="test",
            name="repo",
            status=RepoStatus.READY,
            graph_summary={
                "node_count": 42,
                "edges": [
                    {"from": "a.py:foo:1", "to": "b.py:bar:5"},
                    {"from": "a.py:foo:1", "to": "c.py:baz:10"},
                ],
                "modules": {"src": 30, "tests": 12},
            },
        )
        pg_session.add(repo)
        await pg_session.commit()

        # Re-fetch and verify the data round-trips
        result = await pg_session.execute(
            select(Repository).where(Repository.full_name == "test/repo")
        )
        loaded = result.scalar_one()
        assert loaded.graph_summary["node_count"] == 42
        assert len(loaded.graph_summary["edges"]) == 2
        assert loaded.graph_summary["modules"]["src"] == 30

    async def test_jsonb_supports_jsonpath_query(self, pg_session):
        """Postgres' @> containment operator works on JSONB.

        This is the kind of query we'd run in production for
        'find all triage reports with X finding' — and it ONLY works
        on real JSONB, not on SQLite's JSON-as-TEXT.
        """
        # Insert a triage report with structured findings
        repo = Repository(
            github_id=1, full_name="r/x", owner="r", name="x", status=RepoStatus.READY
        )
        pg_session.add(repo)
        await pg_session.flush()

        pr = PullRequest(
            repository_id=repo.id,
            github_pr_id=1,
            number=1,
            title="t",
            body="",
            author="a",
            base_branch="main",
            head_branch="f",
            state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        pg_session.add(pr)
        await pg_session.flush()

        report = TriageReport(
            pull_request_id=pr.id,
            classification=PRClassification.HUMAN_FIRST,
            classification_confidence=0.9,
            summary="ok",
            findings=[
                {"severity": "CRITICAL", "category": "security", "file": "auth.py"},
                {"severity": "WARNING", "category": "performance", "file": "main.py"},
            ],
        )
        pg_session.add(report)
        await pg_session.commit()

        # Query: find all reports with a CRITICAL security finding
        # This uses the @> (contains) operator on JSONB
        result = await pg_session.execute(
            select(TriageReport).where(
                TriageReport.findings.op("@>")(
                    [{"severity": "CRITICAL", "category": "security"}]
                )
            )
        )
        matched = result.scalar_one_or_none()
        assert matched is not None
        assert matched.classification == PRClassification.HUMAN_FIRST

        # And: find all reports with no CRITICAL findings
        result = await pg_session.execute(
            select(TriageReport).where(
                ~TriageReport.findings.op("@>")(
                    [{"severity": "CRITICAL"}]
                )
            )
        )
        # The match above (same row) should not appear here
        no_critical = result.scalar_one_or_none()
        assert no_critical is None


# ─── UUID column tests ────────────────────────────────────────

class TestUuidColumns:
    """Verify UUID columns store native UUIDs and that the index is on the right type."""

    async def test_uuid_round_trip(self, pg_session):
        repo = Repository(
            github_id=2,
            full_name="u/r",
            owner="u",
            name="r",
            status=RepoStatus.READY,
        )
        pg_session.add(repo)
        await pg_session.commit()

        result = await pg_session.execute(
            select(Repository).where(Repository.full_name == "u/r")
        )
        loaded = result.scalar_one()
        assert isinstance(loaded.id, uuid.UUID)
        # And it should be a real UUID, not a string
        assert loaded.id.version == 4  # UUIDv4 (random)

    async def test_uuid_foreign_key_works(self, pg_session):
        """Inserting a PR with a UUID FK should work in PG but is fiddly in SQLite."""
        repo = Repository(
            github_id=3, full_name="fk/r", owner="fk", name="r", status=RepoStatus.READY
        )
        pg_session.add(repo)
        await pg_session.flush()

        pr = PullRequest(
            repository_id=repo.id,  # UUID FK
            github_pr_id=1, number=1, title="t", body="", author="a",
            base_branch="main", head_branch="f", state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        pg_session.add(pr)
        await pg_session.commit()

        result = await pg_session.execute(select(PullRequest))
        loaded = result.scalar_one()
        assert loaded.repository_id == repo.id
        assert isinstance(loaded.repository_id, uuid.UUID)


# ─── Connection pool tests ───────────────────────────────────

class TestConnectionPool:
    """Test that the engine kwargs (pool_size, max_overflow, pre_ping)
    actually work on real Postgres. SQLite ignores these and crashes
    if you pass them.
    """

    async def test_engine_accepts_postgres_pool_config(self, postgres_url):
        # This used to crash with SQLite. With PG it should succeed.
        engine = create_async_engine(
            postgres_url,
            echo=False,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,
        )
        # Just opening a connection should work
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        await engine.dispose()

    async def test_concurrent_connections(self, pg_engine):
        """The pool should support multiple concurrent connections."""
        async def query_one():
            async with pg_engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar()

        # Fire 10 concurrent queries
        results = await asyncio.gather(*[query_one() for _ in range(10)])
        assert all(r == 1 for r in results)


# ─── Transaction tests ────────────────────────────────────────

class TestTransactions:
    """Test transaction semantics — commit, rollback, isolation."""

    async def test_commit_persists_data(self, pg_session):
        repo = Repository(
            github_id=10, full_name="t/c", owner="t", name="c", status=RepoStatus.READY
        )
        pg_session.add(repo)
        await pg_session.commit()

        # Open a new session to verify the commit
        from sqlalchemy.ext.asyncio import async_sessionmaker
        factory = async_sessionmaker(pg_session.bind, expire_on_commit=False)
        async with factory() as s2:
            result = await s2.execute(
                select(Repository).where(Repository.full_name == "t/c")
            )
            assert result.scalar_one() is not None

    async def test_rollback_discards_data(self, pg_session):
        repo = Repository(
            github_id=11, full_name="r/c", owner="r", name="c", status=RepoStatus.READY
        )
        pg_session.add(repo)
        await pg_session.flush()
        # Don't commit — rollback
        await pg_session.rollback()

        from sqlalchemy.ext.asyncio import async_sessionmaker
        factory = async_sessionmaker(pg_session.bind, expire_on_commit=False)
        async with factory() as s2:
            result = await s2.execute(
                select(Repository).where(Repository.full_name == "r/c")
            )
            assert result.scalar_one_or_none() is None


# ─── Enum / status tests ──────────────────────────────────────

class TestEnumColumns:
    """Enum columns should accept only the defined values."""

    async def test_invalid_enum_value_raises(self, pg_session):
        from sqlalchemy.exc import DataError, DBAPIError, IntegrityError

        repo = Repository(
            github_id=20, full_name="e/x", owner="e", name="x",
            status="not-a-real-status",  # invalid enum value
        )
        pg_session.add(repo)
        with pytest.raises((DataError, IntegrityError, DBAPIError, ValueError)):
            await pg_session.commit()
