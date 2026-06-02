from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from modules.db.errors import DatabasePoolNotInitializedError
from modules.db.settings import DatabaseSettings

_pool: AsyncConnectionPool | None = None


def create_pool(settings: DatabaseSettings) -> AsyncConnectionPool:
    """Create a new AsyncConnectionPool from settings.

    The pool is created with ``open=False`` and ``dict_row`` row factory.
    It does not open any connection until ``open_pool()`` is called.
    """
    return AsyncConnectionPool(
        conninfo=settings.dsn,
        min_size=settings.min_size,
        max_size=settings.max_size,
        timeout=settings.connect_timeout,
        open=False,
        configure=lambda conn: conn,
        kwargs={
            "row_factory": dict_row,
            "application_name": settings.application_name,
        },
    )


def set_pool(pool: AsyncConnectionPool) -> None:
    """Set the global pool instance."""
    global _pool
    _pool = pool


def get_pool() -> AsyncConnectionPool:
    """Return the global pool or raise if not set."""
    if _pool is None:
        raise DatabasePoolNotInitializedError(
            "Database pool not initialized. Call set_pool() or create_pool() first."
        )
    return _pool


async def open_pool(pool: AsyncConnectionPool) -> None:
    """Open the pool (create background connections)."""
    await pool.open()


async def close_pool(pool: AsyncConnectionPool) -> None:
    """Close the pool and release all connections."""
    await pool.close()


def reset_pool_for_tests() -> None:
    """Reset the global pool reference (for testing only)."""
    global _pool
    _pool = None
