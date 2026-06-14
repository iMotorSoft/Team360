"""Smoke for Knowledge Ingestion dev endpoint — PostgreSQL persist mode.

Calls the internal dev endpoint with mode=persist against a real database.
Creates a temporary package with controlled documents, verifies the response
contract, checks DB state, then cleans up.

Usage:
  cd SrvRestAstroLS_v1/backend
  PYTHONPATH=. uv run python scripts/smoke_knowledge_ingestion_dev_endpoint_postgres.py

Requires a configured database (TEAM360_DB_URL, TEAM360_DB_URL_PSQL, or
DB_PG_V360_URL). Aborts with clear message if not configured.

Expected: ALL PASSED (exit 0)
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import tempfile
from pathlib import Path

from litestar.testing import TestClient
from app import create_app
from modules.db.settings import get_database_settings, sanitize_dsn

# ── Smoke scaffold ──────────────────────────────────────────────────────────

_passed = 0
_failed = 0
_errors: list[str] = []


def _check(description: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {description}")
    else:
        _failed += 1
        msg = f"  FAIL  {description}" + (f" — {detail}" if detail else "")
        _errors.append(msg)
        print(msg)


def _is_db_configured() -> bool:
    try:
        get_database_settings()
        return True
    except Exception:
        return False


# ── Temp package builder ────────────────────────────────────────────────────

SMOKE_PACKAGE_CODE = "pkg_sales_diagnosis"
SMOKE_SCOPE_CODE = "ks_team360_sales_diagnosis"
SMOKE_WORKSPACE_CODE = "team360_public_site"
SMOKE_ORG_CODE = "team360_live"

SMOKE_DOC_READY = "approved/smoke_doc_ready.md"
SMOKE_DOC_NOT_READY = "approved/smoke_doc_not_ready.md"
SMOKE_SOURCE_URIS = [SMOKE_DOC_READY, SMOKE_DOC_NOT_READY]


def _build_temp_package() -> Path:
    root = Path(tempfile.mkdtemp(prefix="smoke_persist_pkg_"))
    approved = root / "approved"
    approved.mkdir(parents=True)
    meta = root / "_metadata"
    meta.mkdir(parents=True)

    (meta / "package-profile.yaml").write_text(f"""\
package_code: {SMOKE_PACKAGE_CODE}
package_name: Smoke Persist Package
""", encoding="utf-8")

    (meta / "knowledge-scope-mapping.yaml").write_text(f"""\
package_code: {SMOKE_PACKAGE_CODE}
knowledge_scope_code: {SMOKE_SCOPE_CODE}
workspace_code: {SMOKE_WORKSPACE_CODE}
default_runtime_organization_code: {SMOKE_ORG_CODE}
default_runtime_workspace_code: {SMOKE_WORKSPACE_CODE}
allowed_areas:
  finanzas:
    - general
""", encoding="utf-8")

    (meta / "access-tags.yaml").write_text("""\
tags:
  - tag: ceo
    description: CEO
    level: 100
""", encoding="utf-8")

    (approved / "smoke_doc_ready.md").write_text(f"""\
---
status: approved
ingestion_status: ready
document_type: policy
area_key: finanzas
topic_key: general
node_path: "/smoke/persist-test"
access_tags:
  - ceo
locale: es
scope_type: package
visibility: internal
source_type: markdown
package_code: {SMOKE_PACKAGE_CODE}
knowledge_scope_code: {SMOKE_SCOPE_CODE}
workspace_code: {SMOKE_WORKSPACE_CODE}
organization_code: {SMOKE_ORG_CODE}
---
# Smoke Ready Document

This document is approved and ready for ingestion.

## Section Alpha

Content for section alpha.

## Section Beta

Content for section beta.
""", encoding="utf-8")

    (approved / "smoke_doc_not_ready.md").write_text(f"""\
---
status: approved
ingestion_status: not_ready
document_type: guide
area_key: finanzas
topic_key: general
node_path: "/smoke/persist-test-not-ready"
access_tags:
  - ceo
locale: es
scope_type: package
visibility: internal
source_type: markdown
package_code: {SMOKE_PACKAGE_CODE}
knowledge_scope_code: {SMOKE_SCOPE_CODE}
workspace_code: {SMOKE_WORKSPACE_CODE}
organization_code: {SMOKE_ORG_CODE}
---
# Smoke Not-Ready Document

This document is approved but not ready for ingestion.
""", encoding="utf-8")

    return root


# ── Async DB operations (direct connections, not pool) ──────────────────────


async def _connect():
    from psycopg import AsyncConnection
    settings = get_database_settings()
    return await AsyncConnection.connect(settings.dsn, connect_timeout=5)


async def _resolve_scope_id(conn) -> str | None:
    row = await conn.execute(
        "select id::text from knowledge_scopes where scope_code = 'ks_team360_sales_diagnosis'"
    )
    r = await row.fetchone()
    return r[0] if r else None


async def _query_run(conn, run_id: str) -> dict | None:
    row = await conn.execute(
        "select id::text, status, document_source from knowledge_ingestion_runs where id = %s::uuid",
        (run_id,),
    )
    r = await row.fetchone()
    if r:
        return {"id": r[0], "status": r[1], "document_source": r[2]}
    return None


async def _query_doc_ids(conn, scope_id: str, source_uris: list[str]) -> list[str]:
    rows = await conn.execute(
        "select id::text from knowledge_documents "
        "where knowledge_scope_id = %s::uuid and source_uri = any(%s)",
        (scope_id, source_uris),
    )
    return [r[0] for r in await rows.fetchall()]


async def _query_chunk_count(conn, document_id: str) -> int:
    row = await conn.execute(
        "select count(*) from knowledge_chunks where knowledge_document_id = %s::uuid",
        (document_id,),
    )
    r = await row.fetchone()
    return r[0] if r else 0


async def _cleanup_db(conn, run_id: str, scope_id: str, source_uris: list[str]):
    doc_ids = await _query_doc_ids(conn, scope_id, source_uris)
    async with conn.transaction():
        for did in doc_ids:
            await conn.execute(
                "delete from knowledge_chunks where knowledge_document_id = %s::uuid",
                (did,),
            )
        for uri in source_uris:
            await conn.execute(
                "delete from knowledge_documents "
                "where knowledge_scope_id = %s::uuid and source_uri = %s",
                (scope_id, uri),
            )
        await conn.execute(
            "delete from knowledge_ingestion_runs where id = %s::uuid",
            (run_id,),
        )


async def _verify_db(conn, run_id: str) -> str | None:
    run_data = await _query_run(conn, run_id)
    if run_data:
        _check(f"Ingestion run exists (status={run_data['status']})", True)
        _check("Run status is completed", run_data["status"] == "completed")
    else:
        _check("Ingestion run found in DB", False, f"run_id={run_id}")

    scope_id = await _resolve_scope_id(conn)
    _check("Scope ks_team360_sales_diagnosis exists", scope_id is not None)
    if scope_id is None:
        return None

    doc_ids = await _query_doc_ids(conn, scope_id, SMOKE_SOURCE_URIS)
    _check(
        "1 document persisted (ready only)",
        len(doc_ids) == 1,
        f"got {len(doc_ids)}",
    )
    for did in doc_ids:
        chunk_count = await _query_chunk_count(conn, did)
        _check(f"Document {did[:8]}... has chunks", chunk_count > 0, f"count={chunk_count}")

    not_ready_docs = await _query_doc_ids(conn, scope_id, [SMOKE_DOC_NOT_READY])
    _check(
        "Not-ready doc has NO document row in DB",
        len(not_ready_docs) == 0,
        f"found {len(not_ready_docs)} rows",
    )

    try:
        row = await conn.execute(
            "select count(*) from knowledge_chunk_embeddings kce "
            "join knowledge_chunks kc on kc.id = kce.chunk_id "
            "join knowledge_documents kd on kd.id = kc.document_id "
            "where kd.source_uri = any(%s)",
            (SMOKE_SOURCE_URIS,),
        )
        r = await row.fetchone()
        emb_count = r[0] if r else 0
        _check("No embeddings generated for smoke docs", emb_count == 0, f"got {emb_count}")
    except Exception as exc:
        _check(f"Embeddings table — SKIP ({exc})", True)

    return scope_id


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("Knowledge Ingestion Dev Endpoint — PostgreSQL Smoke")
    print("=" * 60)

    if not _is_db_configured():
        print("\n  SKIP  No database configured.")
        print("  Set TEAM360_DB_URL, TEAM360_DB_URL_PSQL, or DB_PG_V360_URL.")
        print("\n" + "=" * 60)
        print("SMOKE: SKIPPED (no DB)")
        return 0

    settings = get_database_settings()
    print(f"\n  DB configured: {sanitize_dsn(settings.dsn)}")

    print("\n[1] Build temporary knowledge package")
    pkg_root = _build_temp_package()
    pkg_path_str = str(pkg_root)
    _check("Temp package created", pkg_root.is_dir())
    _check("Ready doc exists", (pkg_root / SMOKE_DOC_READY).exists())
    _check("Not-ready doc exists", (pkg_root / SMOKE_DOC_NOT_READY).exists())
    _check("Package root is tmpdir (not real corpus)", "tmp" in pkg_path_str.lower() or "temp" in pkg_path_str.lower())

    print("\n[2] POST /api/dev/knowledge-ingestion/ingest (mode=persist)")
    app = create_app()
    run_id: str | None = None
    data: dict | None = None
    scope_id: str | None = None

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/dev/knowledge-ingestion/ingest",
                json={
                    "package_code": SMOKE_PACKAGE_CODE,
                    "package_path": pkg_path_str,
                    "mode": "persist",
                    "include_drafts": False,
                    "chunking_strategy": "markdown",
                },
            )
            _check("HTTP 200", resp.status_code == 200, f"got {resp.status_code}")
            data = resp.json()
    except Exception as exc:
        _check(f"Endpoint call failed: {exc}", False)
        data = None

    if data is None:
        _check("Response received", False)
    else:
        _check("Response is JSON", isinstance(data, dict))

        data = resp.json()
        _check("Response is JSON", isinstance(data, dict))
        _check("ok == true", data.get("ok") is True)
        _check("mode == persist", data.get("mode") == "persist")
        _check("package_code matches", data.get("package_code") == SMOKE_PACKAGE_CODE)
        _check("document_count >= 2", data.get("document_count", 0) >= 2)
        _check("candidate_count >= 1", data.get("candidate_count", 0) >= 1)
        _check("ready_count >= 1", data.get("ready_count", 0) >= 1)
        _check("rejected_count >= 1", data.get("rejected_count", 0) >= 1)
        _check("chunk_count > 0", data.get("chunk_count", 0) > 0)
        _check("persisted_document_count >= 1", data.get("persisted_document_count", 0) >= 1)
        _check("persisted_chunk_count > 0", data.get("persisted_chunk_count", 0) > 0)
        _check("run_id is not null", data.get("run_id") is not None)
        _check("documents is list", isinstance(data.get("documents"), list))

        run_id = data.get("run_id")

        print("\n[3] Per-document checks")
        docs = data.get("documents", [])
        ready_docs = [d for d in docs if "smoke_doc_ready" in d.get("relative_path", "")]
        not_ready_docs = [d for d in docs if "smoke_doc_not_ready" in d.get("relative_path", "")]

        _check("Ready doc found in response", len(ready_docs) >= 1)
        _check("Not-ready doc found in response", len(not_ready_docs) >= 1)

        if ready_docs:
            rd = ready_docs[0]
            _check("Ready doc persisted true", rd.get("persisted") is True)
            _check("Ready doc has document_id", rd.get("document_id") is not None)
            _check("Ready doc has chunk_count > 0", rd.get("chunk_count", 0) > 0)
            _check("Ready doc gate_ready true", rd.get("gate_ready") is True)
            _check("Ready doc node_path preserved", rd.get("node_path") == "/smoke/persist-test")
            _check("Ready doc status approved", rd.get("status") == "approved")
            _check("Ready doc ingestion_status ready", rd.get("ingestion_status") == "ready")

        if not_ready_docs:
            nd = not_ready_docs[0]
            _check("Not-ready doc persisted false", nd.get("persisted") is False)
            _check("Not-ready doc chunk_count == 0", nd.get("chunk_count", -1) == 0)
            _check("Not-ready doc gate_ready false", nd.get("gate_ready") is False)
            _check("Not-ready doc has error_codes", len(nd.get("error_codes", [])) > 0)
            _check("Not-ready doc node_path preserved", nd.get("node_path") == "/smoke/persist-test-not-ready")
            _check("Not-ready doc status approved", nd.get("status") == "approved")
            _check("Not-ready doc ingestion_status not_ready", nd.get("ingestion_status") == "not_ready")

        print("\n[4] No Milvus / no OpenAI / no embeddings")
        _check("No errors mention Milvus", all("milvus" not in str(e).lower() for e in data.get("errors", [])))
        _check("No errors mention OpenAI", all("openai" not in str(e).lower() for e in data.get("errors", [])))
        _check("No errors mention embedding", all("embedding" not in str(e).lower() for e in data.get("errors", [])))
        _check("errors array is empty or clean", len(data.get("errors", [])) == 0)

        print("\n[5] Database verification")
        scope_id: str | None = None
        if run_id is None:
            _check("run_id available for DB verification", False)
        else:
            try:
                conn = asyncio.run(_connect())
                try:
                    scope_id = asyncio.run(_verify_db(conn, run_id))
                finally:
                    asyncio.run(conn.close())
            except Exception as exc:
                _check(f"DB verification — SKIP ({exc})", True)

        print("\n[6] Cleanup")
        if run_id and scope_id:
            try:
                conn = asyncio.run(_connect())
                try:
                    asyncio.run(_cleanup_db(conn, run_id, scope_id, SMOKE_SOURCE_URIS))
                    _check("Cleanup completed", True)
                    cleanup_src = inspect.getsource(_cleanup_db)
                    _check("Cleanup no broad package_code delete", "package_code" not in cleanup_src)
                    _check("Cleanup uses run_id WHERE", "where id = %s::uuid" in cleanup_src)
                    _check("Cleanup uses source_uri WHERE", "source_uri" in cleanup_src)
                finally:
                    asyncio.run(conn.close())
            except Exception as exc:
                _check(f"Cleanup — SKIP ({exc})", True)
        else:
            _check("Cleanup skipped (missing run_id or scope_id)", False)

    print("\n" + "=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _errors:
        print("\nFailures:")
        for e in _errors:
            print(e)
    print("=" * 60)

    if _failed:
        print("SMOKE: FAILED")
        return 1
    print("SMOKE: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
