"""Real PostgreSQL pool contract for the public Diagnosis scope resolver."""

from __future__ import annotations

import os
from uuid import UUID

import pytest

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.sales_diagnosis_runtime import KnowledgeScopeContext
from modules.sales_diagnosis_runtime.knowledge_scope_resolver import (
    PostgresKnowledgeScopeResolver,
)


REQUIRE = "requires TEAM360_DIAGNOSIS_SCOPE_POSTGRES_TEST=1"


@pytest.mark.skipif(
    os.environ.get("TEAM360_DIAGNOSIS_SCOPE_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
@pytest.mark.anyio
async def test_resolver_uses_real_async_connection_pool_contract():
    try:
        settings = get_database_settings(min_size=1, max_size=1)
    except Exception as exc:
        pytest.skip(f"PostgreSQL settings unavailable: {type(exc).__name__}")

    pool = create_pool(settings)
    await open_pool(pool)
    try:
        resolver = PostgresKnowledgeScopeResolver(pool=pool)
        result = await resolver.resolve_scope_id(
            KnowledgeScopeContext(
                organization_code="team360_live",
                workspace_code="team360_public_site",
                package_code="pkg_sales_diagnosis",
                knowledge_scope_code="ks_team360_sales_diagnosis",
            )
        )
    finally:
        await close_pool(pool)

    assert result is not None
    assert str(UUID(result)) == result
