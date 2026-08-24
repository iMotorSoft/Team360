"""Application service for the explicit Flow demo cleanup action."""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .case_cleanup_repository import FlowCaseCleanupPostgresRepository


class FlowCaseCleanupService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowCaseCleanupPostgresRepository | None = None,
    ) -> None:
        self._pool = pool
        self._repository = repository or FlowCaseCleanupPostgresRepository()

    async def clear_cases(self) -> dict:
        async with transaction(self._pool) as conn:
            return await self._repository.clear_cases(conn)
