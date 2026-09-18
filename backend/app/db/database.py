"""
Async SQLAlchemy engine and session factory.

The FastAPI app talks to Postgres asynchronously (via asyncpg) so that
awaiting a DB write never blocks the event loop that's also servicing
WebSocket connections.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields a scoped async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables on startup. Fine for this project; a real
    production system would use Alembic migrations instead."""
    async with engine.begin() as conn:
        from app.db import models  # noqa: F401  (ensure models are registered)

        await conn.run_sync(Base.metadata.create_all)
