"""Smoke test for sales diagnosis conversation state persistence.

Applies migration 007, creates/loads/updates a ConversationState
via raw SQL against a real PostgreSQL 18 instance.
Requires TEAM360_DB_URL or TEAM360_DB_URL_PSQL environment variable.

Usage:
    TEAM360_DB_URL=postgresql://user:pass@host:port/dbname \\
        uv run python scripts/smoke_sales_diagnosis_state_postgres.py

No real LLM, no Milvus, no other tables touched.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse

from modules.sales_diagnosis_runtime.state_repository import (
    ConversationStateSerializer,
    MIGRATION_FILE,
)
from psycopg_pool import AsyncConnectionPool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Smoke logic
# ---------------------------------------------------------------------------

TABLE = "sales_diagnosis_conversation_states"


def _make_test_state() -> dict[str, Any]:
    from uuid import uuid4

    state = ConversationStateSerializer.to_dict(
        ConversationStateSerializer.from_dict({
            "session_id": f"smoke_{uuid4()}",
            "assistant_instance_code": "team360_sales_diagnosis",
            "package_code": "pkg_sales_diagnosis",
            "knowledge_scope_code": "ks_team360_sales_diagnosis",
            "slots": {"industry": "retail", "size": "medium"},
            "history_summary": "User asked about automation possibilities.",
            "turn_count": 3,
            "risk_flags": ["pricing_sensitive"],
            "last_sources": [],
            "pending_questions": ["What channel do you use?"],
        })
    )
    return state


async def run_smoke(db_url: str) -> None:
    sanitized = _sanitize_url(db_url)
    print(f"=== Sales Diagnosis State PostgreSQL Smoke ===")
    print(f"DB URL: {sanitized}")
    print(f"Table: {TABLE}")
    print()

    pool = AsyncConnectionPool(
        conninfo=db_url,
        min_size=1,
        max_size=2,
        timeout=10,
        open=False,
        kwargs={"application_name": "team360-smoke-sd-state"},
    )
    await pool.open()
    print("Pool opened.")

    try:
        async with pool.connection() as conn:
            # ---- 1. apply migration ----
            migration_sql = _load_migration_sql()
            async with conn.cursor() as cur:
                await cur.execute(migration_sql)
            await conn.commit()
            print("Migration 007 applied (idempotent).")

            # ---- 2. generate test state ----
            test_state = _make_test_state()
            session_id = test_state["session_id"]
            print(f"Test session_id: {session_id}")

            # ---- 3. INSERT ----
            insert_sql = (
                f"INSERT INTO {TABLE} "
                f"(session_id, assistant_instance_code, package_code, "
                f"knowledge_scope_code, state_jsonb, "
                f"created_at_utc, updated_at_utc) "
                f"VALUES (%(session_id)s, %(assistant_instance_code)s, "
                f"%(package_code)s, %(knowledge_scope_code)s, "
                f"%(state_jsonb)s::jsonb, now(), now())"
            )
            async with conn.cursor() as cur:
                await cur.execute(insert_sql, {
                    "session_id": session_id,
                    "assistant_instance_code": test_state["assistant_instance_code"],
                    "package_code": test_state["package_code"],
                    "knowledge_scope_code": test_state["knowledge_scope_code"],
                    "state_jsonb": json.dumps(test_state),
                })
            await conn.commit()
            print("INSERT OK.")

            # ---- 4. SELECT and verify ----
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT state_jsonb FROM {TABLE} WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
                row = await cur.fetchone()
            assert row is not None, "Row not found after INSERT"
            raw_jsonb = row[0]
            assert isinstance(raw_jsonb, dict), f"Expected dict, got {type(raw_jsonb)}"
            loaded = ConversationStateSerializer.from_dict(raw_jsonb)
            assert loaded.session_id == session_id
            assert loaded.turn_count == 3
            assert loaded.slots == {"industry": "retail", "size": "medium"}
            assert loaded.history_summary == "User asked about automation possibilities."
            assert loaded.pending_questions == ["What channel do you use?"]
            print("SELECT + verify OK.")

            # ---- 5. UPSERT (update turn_count) ----
            test_state["turn_count"] = 5
            upsert_sql = (
                f"INSERT INTO {TABLE} "
                f"(session_id, assistant_instance_code, package_code, "
                f"knowledge_scope_code, state_jsonb, "
                f"created_at_utc, updated_at_utc) "
                f"VALUES (%(session_id)s, %(assistant_instance_code)s, "
                f"%(package_code)s, %(knowledge_scope_code)s, "
                f"%(state_jsonb)s::jsonb, now(), now()) "
                f"ON CONFLICT (session_id) DO UPDATE SET "
                f"state_jsonb = EXCLUDED.state_jsonb, "
                f"updated_at_utc = now()"
            )
            async with conn.cursor() as cur:
                await cur.execute(upsert_sql, {
                    "session_id": session_id,
                    "assistant_instance_code": test_state["assistant_instance_code"],
                    "package_code": test_state["package_code"],
                    "knowledge_scope_code": test_state["knowledge_scope_code"],
                    "state_jsonb": json.dumps(test_state),
                })
            await conn.commit()
            print("UPSERT OK.")

            # ---- 6. Verify updated turn_count ----
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT state_jsonb FROM {TABLE} WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
                row = await cur.fetchone()
            assert row is not None
            updated = ConversationStateSerializer.from_dict(row[0])
            assert updated.turn_count == 5, f"Expected turn_count=5, got {updated.turn_count}"
            assert updated.history_summary == "User asked about automation possibilities."
            print("UPSERT verify OK.")

            # ---- 7. Check updated_at_utc changed ----
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT created_at_utc, updated_at_utc "
                    f"FROM {TABLE} WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
                row = await cur.fetchone()
            assert row is not None
            created_ts, updated_ts = row
            assert created_ts is not None
            assert updated_ts is not None
            assert updated_ts >= created_ts, (
                f"updated_at {updated_ts} < created_at {created_ts}"
            )
            print(f"Timestamps: created={created_ts}, updated={updated_ts}")

            # ---- 8. Cleanup ----
            async with conn.cursor() as cur:
                await cur.execute(
                    f"DELETE FROM {TABLE} WHERE session_id = %(sid)s",
                    {"sid": session_id},
                )
            await conn.commit()
            print("Cleanup OK.")

    finally:
        await pool.close()
        print("Pool closed.")

    print()
    print("=== SMOKE PASSED ===")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    db_url = _resolve_db_url()
    asyncio.run(run_smoke(db_url))
    sys.exit(0)


if __name__ == "__main__":
    main()
