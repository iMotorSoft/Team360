"""Smoke test for AsyncPostgresConversationStateRepository.

Validates the async boundary: save/load/update/cleanup using
AsyncPostgresConversationStateRepository against a real PostgreSQL 18
instance with psycopg_pool.AsyncConnectionPool.

Requires TEAM360_DB_URL or TEAM360_DB_URL_PSQL environment variable.

Usage:
    TEAM360_DB_URL=postgresql://user:pass@host:port/dbname \\
        uv run python scripts/smoke_sales_diagnosis_state_postgres_async.py

No real LLM, no Milvus, no other tables touched.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from psycopg_pool import AsyncConnectionPool

from modules.sales_diagnosis_runtime.state_repository import (
    AsyncPostgresConversationStateRepository,
    ConversationStateSerializer,
    MIGRATION_FILE,
)


def _resolve_db_url() -> str:
    url = os.environ.get("TEAM360_DB_URL", "").strip()
    if url:
        return url
    url = os.environ.get("TEAM360_DB_URL_PSQL", "").strip()
    if url:
        return url
    print("ERROR: Set TEAM360_DB_URL or TEAM360_DB_URL_PSQL", file=sys.stderr)
    sys.exit(1)


def _sanitize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.password:
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{parsed.hostname}:{parsed.port}"
        parsed = parsed._replace(netloc=netloc)
    return parsed.geturl()


def _load_migration_sql() -> str:
    from pathlib import Path

    backend_root = Path(__file__).resolve().parent.parent
    migration_path = backend_root / MIGRATION_FILE
    if not migration_path.exists():
        print(f"ERROR: Migration file not found: {migration_path}", file=sys.stderr)
        sys.exit(1)
    return migration_path.read_text(encoding="utf-8")


async def run_smoke(db_url: str) -> None:
    sanitized = _sanitize_url(db_url)
    print("=== Async Sales Diagnosis State PostgreSQL Smoke ===")
    print(f"DB URL: {sanitized}")
    print()

    pool = AsyncConnectionPool(
        conninfo=db_url,
        min_size=1,
        max_size=2,
        timeout=10,
        open=False,
        kwargs={"application_name": "team360-smoke-sd-async"},
    )
    await pool.open()
    print("Pool opened.")

    try:
        # ---- 1. apply migration ----
        migration_sql = _load_migration_sql()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(migration_sql)
            await conn.commit()
        print("Migration 007 applied (idempotent).")

        # ---- 2. instantiate repository ----
        repo = AsyncPostgresConversationStateRepository(pool=pool)
        print("AsyncPostgresConversationStateRepository instantiated.")

        # ---- 3. prepare test state ----
        from uuid import uuid4

        from modules.sales_diagnosis_runtime.contracts import (
            ConversationState,
            RetrievedChunk,
        )

        session_id = f"async_smoke_{uuid4()}"
        state = ConversationState(
            session_id=session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            slots={"industry": "retail", "size": "medium"},
            history_summary="User asked about automation possibilities.",
            turn_count=3,
            risk_flags=["pricing_sensitive"],
            last_sources=[
                RetrievedChunk(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    knowledge_scope_id="ks_team360_sales_diagnosis",
                    source_uri="https://example.com/doc1",
                    title="Example Doc",
                    node_path="/root/section1",
                    score=0.95,
                    content_preview="This is a preview.",
                    content="This is the full content.",
                ),
            ],
            pending_questions=["What channel do you use?"],
        )
        print(f"Test state created. session_id={session_id}")

        # ---- 4. save ----
        await repo.save(state)
        print("save() OK.")

        # ---- 5. load ----
        loaded = await repo.load(session_id)
        assert loaded is not None, "Loaded state is None"
        assert loaded.session_id == session_id
        assert loaded.turn_count == 3
        assert loaded.slots == {"industry": "retail", "size": "medium"}
        assert loaded.history_summary == "User asked about automation possibilities."
        assert loaded.pending_questions == ["What channel do you use?"]
        assert len(loaded.last_sources) == 1
        assert loaded.last_sources[0].chunk_id == "chunk_001"
        assert loaded.last_sources[0].score == 0.95
        print("load() + verify OK.")

        # ---- 6. update (save with modified turn_count) ----
        updated_state = ConversationState(
            session_id=session_id,
            assistant_instance_code=state.assistant_instance_code,
            package_code=state.package_code,
            knowledge_scope_code=state.knowledge_scope_code,
            slots=state.slots,
            history_summary="Updated summary after second turn.",
            turn_count=5,
            risk_flags=state.risk_flags,
            last_sources=state.last_sources,
            pending_questions=state.pending_questions,
        )
        await repo.save(updated_state)
        print("save() (update) OK.")

        # ---- 7. verify update ----
        reloaded = await repo.load(session_id)
        assert reloaded is not None
        assert reloaded.turn_count == 5
        assert reloaded.history_summary == "Updated summary after second turn."
        print("Updated state verify OK.")

        # ---- 8. load non-existent ----
        missing = await repo.load("nonexistent_session_id_xyz")
        assert missing is None
        print("load(non-existent) returns None OK.")

        # ---- 9. cleanup ----
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"DELETE FROM {repo.TABLE_NAME} WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
            await conn.commit()
        print("Cleanup OK.")

    finally:
        await pool.close()
        print("Pool closed.")

    print()
    print("=== ASYNC SMOKE PASSED ===")


def main() -> None:
    db_url = _resolve_db_url()
    import asyncio

    asyncio.run(run_smoke(db_url))
    sys.exit(0)


if __name__ == "__main__":
    main()
