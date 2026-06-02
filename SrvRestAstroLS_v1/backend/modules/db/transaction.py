from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from modules.db.errors import DatabaseExecutionError


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    return dict(row._mapping)


async def fetch_one(
    conn: AsyncConnection,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Execute a query and return one row as a dict."""
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
            if row is None:
                return None
            return _row_to_dict(row)
    except Exception as exc:
        raise DatabaseExecutionError(str(exc)) from exc


async def fetch_all(
    conn: AsyncConnection,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute a query and return all rows as a list of dicts."""
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()
            return [_row_to_dict(row) for row in rows]
    except Exception as exc:
        raise DatabaseExecutionError(str(exc)) from exc


async def execute(
    conn: AsyncConnection,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> int | None:
    """Execute a statement and return the row count if available."""
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            return cur.rowcount
    except Exception as exc:
        raise DatabaseExecutionError(str(exc)) from exc


@asynccontextmanager
async def transaction(pool: AsyncConnectionPool) -> AsyncIterator[AsyncConnection]:
    """Context manager that yields a connection with an open transaction.

    Commits on success, rolls back on exception.
    """
    async with pool.connection() as conn:
        async with conn.transaction():
            try:
                yield conn
            except BaseException:
                raise
