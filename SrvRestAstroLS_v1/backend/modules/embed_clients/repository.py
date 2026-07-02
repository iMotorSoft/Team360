from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import fetch_one
from modules.embed_clients.models import EmbedClient


class EmbedClientRepository:
    """Abstract base for embed client lookups."""

    async def load(self, client_id: str) -> EmbedClient | None:
        raise NotImplementedError


class InMemoryEmbedClientRepository(EmbedClientRepository):
    """In-memory repository for testing without PostgreSQL."""

    def __init__(self, clients: dict[str, EmbedClient] | None = None) -> None:
        self._clients: dict[str, EmbedClient] = {}
        if clients:
            self._clients.update(clients)

    def add(self, client: EmbedClient) -> None:
        self._clients[client.client_id] = client

    async def load(self, client_id: str) -> EmbedClient | None:
        return self._clients.get(client_id)


class PostgresEmbedClientRepository(EmbedClientRepository):
    """PostgreSQL-backed repository using the global connection pool."""

    LOAD_SQL = """
        SELECT
            client_id,
            hmac_secret,
            assistant_instance_code,
            organization_code,
            workspace_code,
            package_code,
            knowledge_scope_code,
            allowed_origins,
            is_active
        FROM embed_clients
        WHERE client_id = %(client_id)s
    """

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def load(self, client_id: str) -> EmbedClient | None:
        async with self._pool.connection() as conn:
            row = await fetch_one(conn, self.LOAD_SQL, {"client_id": client_id})
        if row is None:
            return None
        return EmbedClient.from_row(row)
