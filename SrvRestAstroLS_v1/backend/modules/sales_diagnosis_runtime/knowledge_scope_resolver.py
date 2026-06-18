"""PostgreSQL-backed knowledge scope resolver.

PostgreSQL is the source of truth for scope identity and ownership.
Milvus receives already-resolved UUIDs — no code-to-UUID inference in vector search.

Ownership chain:
    workspace (slug + organization_code in metadata_jsonb)
    -> knowledge_scopes (workspace_id, scope_code)
    -> knowledge_scope_bindings (binding_type='automation_package', bound_entity_id)

Archives:
    There is no dedicated organizations table yet. organization_code is stored
    in core_workspaces.metadata_jsonb -> 'organization_code'.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from modules.sales_diagnosis_runtime.contracts import KnowledgeScopeContext
from modules.sales_diagnosis_runtime.errors import (
    SalesDiagnosisRuntimeError,
)


class ScopeResolutionError(SalesDiagnosisRuntimeError):
    """Raised when scope resolution fails due to configuration or connectivity."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class KnowledgeScopeResolver(Protocol):
    """Resolve a KnowledgeScopeContext to a knowledge_scope_id UUID string.

    Returns None when the scope cannot be resolved (unknown codes, wrong
    ownership, ambiguous context). Never falls back to a default scope.
    """

    async def resolve_scope_id(
        self,
        context: KnowledgeScopeContext,
    ) -> str | None:
        ...


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------


_RESOLVE_SCOPE_SQL = """
select ks.id::text
from knowledge_scopes ks
join core_workspaces w on w.id = ks.workspace_id
where w.slug = %(workspace_code)s
  and ks.scope_code = %(knowledge_scope_code)s
  and ks.status = 'active'
  and w.status = 'active'
  and w.metadata_jsonb->>'organization_code' = %(organization_code)s
"""

_VERIFY_PACKAGE_BINDING_SQL = """
select 1
from knowledge_scope_bindings ksb
join automation_packages ap on ap.id = ksb.bound_entity_id
where ksb.knowledge_scope_id = %(scope_id)s::uuid
  and ksb.binding_type = 'automation_package'
  and ksb.bound_entity_id is not null
  and ap.package_code = %(package_code)s
  and ap.status = 'active'
limit 1
"""


@dataclass
class PostgresKnowledgeScopeResolver:
    """Resolves knowledge scope codes to UUIDs via PostgreSQL.

    Uses a psycopg_async connection or pool. When a pool is provided, a
    connection is borrowed for each resolution. When a raw connection is
    provided it is used directly (caller manages lifecycle).
    """

    pool: Any = None
    _connection: Any = None

    @classmethod
    def from_settings(
        cls,
        settings: Any = None,
    ) -> PostgresKnowledgeScopeResolver:
        from modules.db.pool import get_pool
        pool = get_pool()
        return cls(pool=pool)

    async def resolve_scope_id(
        self,
        context: KnowledgeScopeContext,
    ) -> str | None:
        if not context.knowledge_scope_code:
            return None

        conn = await self._get_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    _RESOLVE_SCOPE_SQL,
                    {
                        "workspace_code": context.workspace_code,
                        "knowledge_scope_code": context.knowledge_scope_code,
                        "organization_code": context.organization_code,
                    },
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                scope_id: str = row[0]

                if context.package_code:
                    await cur.execute(
                        _VERIFY_PACKAGE_BINDING_SQL,
                        {
                            "scope_id": scope_id,
                            "package_code": context.package_code,
                        },
                    )
                    binding = await cur.fetchone()
                    if binding is None:
                        return None

                return scope_id
        except Exception as exc:
            raise ScopeResolutionError(
                f"Failed to resolve knowledge scope: {exc}"
            ) from exc
        finally:
            await self._release_connection(conn)

    async def _get_connection(self) -> Any:
        if self._connection is not None:
            return self._connection
        if self.pool is not None:
            return self.pool.connection()
        raise ScopeResolutionError(
            "PostgresKnowledgeScopeResolver has no pool or connection configured."
        )

    async def _release_connection(self, conn: Any) -> None:
        if self._connection is not None:
            return
        if self.pool is not None:
            await conn.close()


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------


@dataclass
class CachedScopeResolver:
    """Wraps a KnowledgeScopeResolver with an in-memory LRU-like cache.

    Cache key: (organization_code, workspace_code, package_code, knowledge_scope_code)
    TTL: 300 seconds by default.
    Negative results (None) are cached for a shorter TTL to avoid stampedes.
    """

    inner: Any
    ttl_seconds: float = 300.0
    negative_ttl_seconds: float = 30.0
    _cache: dict[tuple[str, str, str, str], tuple[float, str | None]] = field(
        default_factory=dict, repr=False
    )

    async def resolve_scope_id(
        self,
        context: KnowledgeScopeContext,
    ) -> str | None:
        key = (
            context.organization_code,
            context.workspace_code,
            context.package_code,
            context.knowledge_scope_code,
        )
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None:
            expires_at, value = cached
            if now < expires_at:
                return value

        result = await self.inner.resolve_scope_id(context)
        ttl = self.negative_ttl_seconds if result is None else self.ttl_seconds
        self._cache[key] = (now + ttl, result)
        return result

    def invalidate(self, context: KnowledgeScopeContext) -> None:
        key = (
            context.organization_code,
            context.workspace_code,
            context.package_code,
            context.knowledge_scope_code,
        )
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()
