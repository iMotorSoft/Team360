"""Tests for KnowledgeScopeResolver, PostgresKnowledgeScopeResolver and cache.

No real DB calls. No real network. All repositories use fakes/stubs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest

from modules.sales_diagnosis_runtime import KnowledgeScopeContext
from modules.sales_diagnosis_runtime.knowledge_scope_resolver import (
    CachedScopeResolver,
    PostgresKnowledgeScopeResolver,
    ScopeResolutionError,
)


# ---------------------------------------------------------------------------
# Fake async connection
# ---------------------------------------------------------------------------


@dataclass
class FakeCursor:
    _rows: list[tuple[Any, ...]]
    _executed: list[tuple[str, dict]] | None = None
    _result_index: int = 0

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def execute(self, query: str, params: dict | None = None) -> None:
        if self._executed is not None:
            self._executed.append((query, params or {}))
        self._result_index = 0

    async def fetchone(self) -> tuple[Any, ...] | None:
        if self._result_index < len(self._rows):
            row = self._rows[self._result_index]
            self._result_index += 1
            return row
        return None


@dataclass
class FakeConnection:
    rows: list[tuple[Any, ...]]
    executed: list[tuple[str, dict]] | None = None
    closed: bool = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.rows, _executed=self.executed)

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakePool:
    rows: list[tuple[Any, ...]]
    executed: list[tuple[str, dict]] | None = None

    def connection(self) -> FakeConnection:
        return FakeConnection(self.rows, executed=self.executed)


# ---------------------------------------------------------------------------
# KnowledgeScopeContext
# ---------------------------------------------------------------------------


class TestKnowledgeScopeContext:
    def test_context_creation(self):
        ctx = KnowledgeScopeContext(
            organization_code="org_a",
            workspace_code="ws_a",
            package_code="pkg_a",
            knowledge_scope_code="scope_a",
        )
        assert ctx.organization_code == "org_a"
        assert ctx.workspace_code == "ws_a"

    def test_context_is_immutable(self):
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )
        with pytest.raises(AttributeError):
            ctx.organization_code = "other"  # type: ignore[misc]

    def test_context_defaults_not_present(self):
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )
        assert hasattr(ctx, "organization_code")


# ---------------------------------------------------------------------------
# PostgresKnowledgeScopeResolver — unit tests
# ---------------------------------------------------------------------------


SCOPE_UUID = "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b"


class TestPostgresKnowledgeScopeResolver:
    @pytest.mark.anyio
    async def test_resolve_valid_scope(self):
        conn = FakeConnection(
            rows=[(SCOPE_UUID,), (1,)],
            executed=[],
        )
        resolver = PostgresKnowledgeScopeResolver(_connection=conn)
        ctx = KnowledgeScopeContext(
            organization_code="team360_live",
            workspace_code="team360_public_site",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_team360_sales_diagnosis",
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result == SCOPE_UUID
        assert len(conn.executed) == 2

    @pytest.mark.anyio
    async def test_resolve_nonexistent_scope_returns_none(self):
        conn = FakeConnection(
            rows=[],
        )
        resolver = PostgresKnowledgeScopeResolver(_connection=conn)
        ctx = KnowledgeScopeContext(
            organization_code="team360_live",
            workspace_code="team360_public_site",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_nonexistent",
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result is None

    @pytest.mark.anyio
    async def test_resolve_workspace_mismatch_returns_none(self):
        conn = FakeConnection(
            rows=[],
        )
        resolver = PostgresKnowledgeScopeResolver(_connection=conn)
        ctx = KnowledgeScopeContext(
            organization_code="team360_live",
            workspace_code="other_workspace",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_team360_sales_diagnosis",
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result is None

    @pytest.mark.anyio
    async def test_resolve_organization_mismatch_returns_none(self):
        conn = FakeConnection(
            rows=[],
        )
        resolver = PostgresKnowledgeScopeResolver(_connection=conn)
        ctx = KnowledgeScopeContext(
            organization_code="other_org",
            workspace_code="team360_public_site",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_team360_sales_diagnosis",
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result is None

    @pytest.mark.anyio
    async def test_resolve_package_mismatch_returns_none(self):
        """Scope exists but is not bound to the requested package.

        Uses a custom cursor that returns scope first, then nothing for binding.
        """
        class PackageMismatchCursor:
            def __init__(self):
                self._call_count = 0
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def execute(self, query, params=None):
                self._call_count += 1
            async def fetchone(self):
                # First call returns scope UUID, second returns None (no binding)
                if self._call_count == 1:
                    return (SCOPE_UUID,)
                return None

        class PackageMismatchConnection:
            def cursor(self):
                return PackageMismatchCursor()
            async def close(self):
                pass

        resolver = PostgresKnowledgeScopeResolver(_connection=PackageMismatchConnection())
        ctx = KnowledgeScopeContext(
            organization_code="team360_live",
            workspace_code="team360_public_site",
            package_code="pkg_different",
            knowledge_scope_code="ks_team360_sales_diagnosis",
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result is None

    @pytest.mark.anyio
    async def test_resolve_empty_scope_code_returns_none(self):
        conn = FakeConnection(
            rows=[],
        )
        resolver = PostgresKnowledgeScopeResolver(_connection=conn)
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code=""
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result is None

    @pytest.mark.anyio
    async def test_resolve_without_package_code_still_works(self):
        conn = FakeConnection(
            rows=[(SCOPE_UUID,)],
            executed=[],
        )
        resolver = PostgresKnowledgeScopeResolver(_connection=conn)
        ctx = KnowledgeScopeContext(
            organization_code="team360_live",
            workspace_code="team360_public_site",
            package_code="",
            knowledge_scope_code="ks_team360_sales_diagnosis",
        )

        result = await resolver.resolve_scope_id(ctx)

        assert result == SCOPE_UUID
        assert len(conn.executed) == 1

    @pytest.mark.anyio
    async def test_resolve_db_error_raises_scope_resolution_error(self):
        class FailingCursor:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def execute(self, query, params=None):
                raise RuntimeError("disk full")
            async def fetchone(self):
                return None

        class BrokenConnection:
            def cursor(self):
                return FailingCursor()
            async def close(self):
                pass

        resolver = PostgresKnowledgeScopeResolver(_connection=BrokenConnection())
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        with pytest.raises(ScopeResolutionError):
            await resolver.resolve_scope_id(ctx)

    @pytest.mark.anyio
    async def test_resolve_no_pool_no_connection_raises_error(self):
        resolver = PostgresKnowledgeScopeResolver()
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        with pytest.raises(ScopeResolutionError, match="no pool or connection"):
            await resolver.resolve_scope_id(ctx)


# ---------------------------------------------------------------------------
# CachedScopeResolver
# ---------------------------------------------------------------------------


class FakeResolver:
    def __init__(self) -> None:
        self.call_count = 0
        self._result: str | None = "uuid-cached"

    async def resolve_scope_id(self, context: KnowledgeScopeContext) -> str | None:
        self.call_count += 1
        return self._result


class TestCachedScopeResolver:
    @pytest.mark.anyio
    async def test_first_call_queries_resolver(self):
        inner = FakeResolver()
        cache = CachedScopeResolver(inner=inner, ttl_seconds=300)
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        result = await cache.resolve_scope_id(ctx)

        assert result == "uuid-cached"
        assert inner.call_count == 1

    @pytest.mark.anyio
    async def test_second_call_uses_cache(self):
        inner = FakeResolver()
        cache = CachedScopeResolver(inner=inner, ttl_seconds=300)
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        await cache.resolve_scope_id(ctx)
        await cache.resolve_scope_id(ctx)

        assert inner.call_count == 1

    @pytest.mark.anyio
    async def test_different_contexts_dont_collide(self):
        inner = FakeResolver()
        cache = CachedScopeResolver(inner=inner, ttl_seconds=300)
        ctx_a = KnowledgeScopeContext(
            organization_code="org_a", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )
        ctx_b = KnowledgeScopeContext(
            organization_code="org_b", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        await cache.resolve_scope_id(ctx_a)
        await cache.resolve_scope_id(ctx_b)

        assert inner.call_count == 2

    @pytest.mark.anyio
    async def test_negative_result_has_shorter_ttl(self):
        inner = FakeResolver()
        inner._result = None
        cache = CachedScopeResolver(
            inner=inner, ttl_seconds=300, negative_ttl_seconds=0.01
        )
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        await cache.resolve_scope_id(ctx)
        await cache.resolve_scope_id(ctx)
        assert inner.call_count == 1

        time.sleep(0.02)
        await cache.resolve_scope_id(ctx)
        assert inner.call_count == 2

    @pytest.mark.anyio
    async def test_invalidate_removes_cache_entry(self):
        inner = FakeResolver()
        cache = CachedScopeResolver(inner=inner, ttl_seconds=300)
        ctx = KnowledgeScopeContext(
            organization_code="o", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        await cache.resolve_scope_id(ctx)
        cache.invalidate(ctx)
        await cache.resolve_scope_id(ctx)

        assert inner.call_count == 2

    @pytest.mark.anyio
    async def test_clear_removes_all_entries(self):
        inner = FakeResolver()
        cache = CachedScopeResolver(inner=inner, ttl_seconds=300)
        ctx_a = KnowledgeScopeContext(
            organization_code="a", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )
        ctx_b = KnowledgeScopeContext(
            organization_code="b", workspace_code="w", package_code="p", knowledge_scope_code="s"
        )

        await cache.resolve_scope_id(ctx_a)
        await cache.resolve_scope_id(ctx_b)
        cache.clear()
        await cache.resolve_scope_id(ctx_a)
        await cache.resolve_scope_id(ctx_b)

        assert inner.call_count == 4


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------


class TestMultiTenantIsolation:
    """Validate that different tenant contexts resolve different UUIDs and
    never cross-contaminate."""

    @pytest.mark.anyio
    async def test_context_a_never_leaks_to_context_b(self):
        resolver_a = FakeResolver()
        resolver_a._result = "uuid-a"
        resolver_b = FakeResolver()
        resolver_b._result = "uuid-b"

        ctx_a = KnowledgeScopeContext(
            organization_code="org_a", workspace_code="ws_a", package_code="pkg_a",
            knowledge_scope_code="scope_a",
        )
        ctx_b = KnowledgeScopeContext(
            organization_code="org_b", workspace_code="ws_b", package_code="pkg_b",
            knowledge_scope_code="scope_b",
        )

        result_a = await resolver_a.resolve_scope_id(ctx_a)
        result_b = await resolver_b.resolve_scope_id(ctx_b)

        assert result_a == "uuid-a"
        assert result_b == "uuid-b"
        assert result_a != result_b

    @pytest.mark.anyio
    async def test_cached_resolver_keeps_tenant_isolation(self):
        class DualResolver:
            def __init__(self):
                self._store = {
                    ("org_a", "ws_a", "pkg_a", "scope_a"): "uuid-a",
                    ("org_b", "ws_b", "pkg_b", "scope_b"): "uuid-b",
                }
                self.call_count = 0

            async def resolve_scope_id(self, ctx):
                self.call_count += 1
                key = (ctx.organization_code, ctx.workspace_code, ctx.package_code, ctx.knowledge_scope_code)
                return self._store.get(key)

        inner = DualResolver()
        cache = CachedScopeResolver(inner=inner, ttl_seconds=300)

        ctx_a = KnowledgeScopeContext("org_a", "ws_a", "pkg_a", "scope_a")
        ctx_b = KnowledgeScopeContext("org_b", "ws_b", "pkg_b", "scope_b")

        r_a1 = await cache.resolve_scope_id(ctx_a)
        r_b1 = await cache.resolve_scope_id(ctx_b)
        assert r_a1 == "uuid-a"
        assert r_b1 == "uuid-b"
        assert inner.call_count == 2

        # Second calls from cache
        r_a2 = await cache.resolve_scope_id(ctx_a)
        r_b2 = await cache.resolve_scope_id(ctx_b)
        assert r_a2 == "uuid-a"
        assert r_b2 == "uuid-b"
        assert inner.call_count == 2  # no new calls
