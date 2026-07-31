"""SQLAlchemy async engine, session factory, and base model."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _build_engine_kwargs() -> dict:
    """Build engine kwargs that work for both Postgres and SQLite.

    SQLite (used in tests) doesn't support connection-pool settings like
    `pool_size` / `max_overflow` / `pool_pre_ping`, so we only apply them
    for non-SQLite dialects.
    """
    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite:
        return {"echo": settings.debug, "future": True}
    return {
        "echo": settings.debug,
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }


engine = create_async_engine(settings.database_url, **_build_engine_kwargs())

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all Pulse ORM models."""


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async database session.

    Commits on success, rolls back on exception. Use as:
        async def endpoint(db: AsyncSession = Depends(get_db)):
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
