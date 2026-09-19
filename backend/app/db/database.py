"""
Async SQLAlchemy engine and session factory.

The FastAPI app talks to Postgres asynchronously (via asyncpg) so that
awaiting a DB write never blocks the event loop that's also servicing
WebSocket connections.
"""
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import get_settings

logger = logging.getLogger(__name__)
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


async def init_db(max_attempts: int = 10, delay_seconds: float = 3.0) -> None:
    """Create all tables on startup, retrying if Postgres isn't actually
    ready to accept connections yet.

    Docker Compose's `depends_on: condition: service_healthy` already waits
    for Postgres's own healthcheck to pass before starting this container,
    but on slower/shared machines there can still be a brief window where
    the healthcheck passes right as the container is scheduled, and the
    very first real connection attempt still loses the race. Retrying a
    few times with a short delay is far more robust than crashing the
    whole app on the first hiccup.
    """
    from app.db import models  # noqa: F401  (ensure models are registered)

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            if attempt > 1:
                logger.info("Connected to the database on attempt %d.", attempt)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Database not ready yet (attempt %d/%d): %s. Retrying in %.0fs...",
                attempt,
                max_attempts,
                exc,
                delay_seconds,
            )
            await asyncio.sleep(delay_seconds)

    raise RuntimeError(
        f"Could not connect to the database after {max_attempts} attempts."
    ) from last_error
