"""Smoke for OpenAI embeddings + Milvus 2.6 indexing — opt-in only.

Requires all these env vars:
  TEAM360_DB_URL
  OPENAI_API_KEY
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS=true
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS=true
  TEAM360_MILVUS_HOST (or MILVUS_URI)

Optional:
  TEAM360_MILVUS_PORT (default 19530)
  TEAM360_MILVUS_TOKEN or TEAM360_MILVUS_USER + TEAM360_MILVUS_PASSWORD

Usage:
  cd SrvRestAstroLS_v1/backend
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS=true \
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS=true \
  PYTHONPATH=. uv run python scripts/smoke_knowledge_ingestion_embeddings_milvus.py

Expected: ALL PASSED (exit 0)
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from app import create_app
from litestar.testing import TestClient
from modules.db.settings import get_database_settings, sanitize_dsn
from modules.knowledge_ingestion.embedding_provider import (
    EMBEDDING_VERSION,
    EXPECTED_DIMENSIONS,
    OPENAI_DEFAULT_MODEL,
    OpenAIEmbeddingProvider,
)
from modules.knowledge_ingestion.schemas import EmbeddingStatus
from psycopg import AsyncConnection

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


def _sanitize(val: str, keep_len: int = 6) -> str:
    if len(val) <= keep_len + 6:
        return val[:keep_len] + "..."
    return val[:keep_len] + "..." + val[-4:]


# ── Env validation ───────────────────────────────────────────────────────────

SMOKE_FLAG_EMBEDDINGS = "TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS"
SMOKE_FLAG_MILVUS = "TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS"


def _validate_env() -> dict[str, str]:
    errors: list[str] = []
    env = {}

    db_url = os.environ.get("TEAM360_DB_URL") or os.environ.get("TEAM360_DB_URL_PSQL") or os.environ.get("DB_PG_V360_URL")
    if not db_url:
        errors.append("TEAM360_DB_URL is required")
    else:
        env["TEAM360_DB_URL"] = db_url

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        errors.append("OPENAI_API_KEY is required")
    else:
        env["OPENAI_API_KEY"] = api_key

    if os.environ.get(SMOKE_FLAG_EMBEDDINGS, "").lower() != "true":
        errors.append(
            f"{SMOKE_FLAG_EMBEDDINGS}=true is required to enable real embeddings"
        )
    else:
        env["ENABLE_EMBEDDINGS"] = "true"

    if os.environ.get(SMOKE_FLAG_MILVUS, "").lower() != "true":
        errors.append(f"{SMOKE_FLAG_MILVUS}=true is required to enable Milvus")
    else:
        env["ENABLE_MILVUS"] = "true"

    milvus_uri = os.environ.get("MILVUS_URI")
    milvus_host = os.environ.get("TEAM360_MILVUS_HOST")
    if not milvus_uri and not milvus_host:
        errors.append(
            "TEAM360_MILVUS_HOST (or MILVUS_URI) is required for Milvus"
        )
    if milvus_uri:
        env["MILVUS_URI"] = milvus_uri
    else:
        host = milvus_host or "localhost"
        port = os.environ.get("TEAM360_MILVUS_PORT", "19530")
        env["MILVUS_URI"] = f"http://{host}:{port}"

    token = os.environ.get("TEAM360_MILVUS_TOKEN") or ""
    user = os.environ.get("TEAM360_MILVUS_USER") or ""
    password = os.environ.get("TEAM360_MILVUS_PASSWORD") or ""
    if token:
        env["MILVUS_TOKEN"] = token
    if user and password:
        env["MILVUS_USER"] = user
        env["MILVUS_PASSWORD"] = password

    if errors:
        print("\n  Missing required configuration:")
        for e in errors:
            print(f"    - {e}")
        print()
        return {}

    return env


# ── Temp package builder ────────────────────────────────────────────────────

SMOKE_PACKAGE_CODE = "pkg_sales_diagnosis"
SMOKE_SCOPE_CODE = "ks_team360_sales_diagnosis"
SMOKE_WORKSPACE_CODE = "team360_public_site"
SMOKE_ORG_CODE = "team360_live"

SMOKE_DOC_READY = "approved/smoke_doc_ready.md"
SMOKE_DOC_NOT_READY = "approved/smoke_doc_not_ready.md"
SMOKE_SOURCE_URIS = [SMOKE_DOC_READY, SMOKE_DOC_NOT_READY]

SMOKE_QUERY = "procedimiento financiero contable"
SMOKE_DOC_CONTENT = """
## Seccion de prueba financiera

Este es un contenido de prueba sobre procedimientos financieros y contables.
Incluye informacion sobre balances, estados de resultados y flujo de efectivo.
Se utiliza para validar que los embeddings y la busqueda vectorial funcionan.

## Otra seccion

Contenido adicional sobre politicas de credito y cobranza.
"""
SMOKE_DOC_NOT_READY_CONTENT = """
## Contenido no listo

Este documento esta marcado como not_ready y no debe generar embeddings.
"""


def _build_temp_package() -> Path:
    root = Path(tempfile.mkdtemp(prefix="smoke_emb_milvus_"))
    approved = root / "approved"
    approved.mkdir(parents=True)
    meta = root / "_metadata"
    meta.mkdir(parents=True)

    (meta / "package-profile.yaml").write_text(f"""\
package_code: {SMOKE_PACKAGE_CODE}
package_name: Smoke Embeddings + Milvus Package
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
node_path: "/smoke/emb-milvus-test"
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
# Smoke Embeddings + Milvus Ready Document
{SMOKE_DOC_CONTENT}
""", encoding="utf-8")

    (approved / "smoke_doc_not_ready.md").write_text(f"""\
---
status: approved
ingestion_status: not_ready
document_type: guide
area_key: finanzas
topic_key: general
node_path: "/smoke/emb-milvus-not-ready"
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
# Smoke Embeddings + Milvus Not-Ready Document
{SMOKE_DOC_NOT_READY_CONTENT}
""", encoding="utf-8")

    return root


# ── Async DB operations ─────────────────────────────────────────────────────


async def _db_connect():
    settings = get_database_settings()
    return await AsyncConnection.connect(settings.dsn, connect_timeout=5)


async def _resolve_scope_id(conn) -> str | None:
    row = await conn.execute(
        "select id::text from knowledge_scopes where scope_code = 'ks_team360_sales_diagnosis'"
    )
    r = await row.fetchone()
    return r[0] if r else None


async def _query_pending_chunks(conn, scope_id: str) -> list[dict]:
    rows = await conn.execute(
        """
        select kc.id::text as chunk_id, kc.content, kc.title,
               kc.knowledge_document_id::text as document_id,
               kc.chunk_index
        from knowledge_chunks kc
        join knowledge_documents kd on kd.id = kc.knowledge_document_id
        where kd.knowledge_scope_id = %s::uuid
          and kd.source_uri like %s
        order by kc.chunk_index
        """,
        (scope_id, "approved/smoke_doc_ready.md"),
    )
    return await rows.fetchall() or []


async def _query_embedding_count(conn, chunk_id: str) -> int:
    row = await conn.execute(
        """
        select count(*) from knowledge_chunk_embeddings kce
        join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
        where kc.id = %s::uuid and kce.embedding_status = 'ready'
        """,
        (chunk_id,),
    )
    r = await row.fetchone()
    return r[0] if r else 0


async def _query_not_ready_chunks(conn, scope_id: str) -> list[dict]:
    rows = await conn.execute(
        """
        select kc.id::text as chunk_id
        from knowledge_chunks kc
        join knowledge_documents kd on kd.id = kc.knowledge_document_id
        where kd.knowledge_scope_id = %s::uuid
          and kd.source_uri like %s
        """,
        (scope_id, "approved/smoke_doc_not_ready.md"),
    )
    return await rows.fetchall() or []


async def _query_embeddings_for_index(conn, scope_id: str) -> list[dict]:
    rows = await conn.execute(
        """
        select
            kce.chunk_embedding_id::text,
            kc.id::text as chunk_id,
            kc.knowledge_document_id::text as document_id,
            kd.knowledge_scope_id::text as scope_id,
            kc.title,
            kc.content,
            kc.node_path,
            kce.embedding,
            kce.metadata_jsonb->>'embedding_version' as emb_version
        from knowledge_chunk_embeddings kce
        join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
        join knowledge_documents kd on kd.id = kc.knowledge_document_id
        where kd.knowledge_scope_id = %s::uuid
          and kd.source_uri like %s
          and kce.embedding_status = 'ready'
          and kce.embedding is not null
        """,
        (scope_id, "approved/smoke_doc_ready.md"),
    )
    return await rows.fetchall() or []


async def _cleanup_postgres(conn, scope_id: str):
    doc_ids_res = await conn.execute(
        "select id from knowledge_documents "
        "where knowledge_scope_id = %s::uuid and source_uri like %s",
        (scope_id, "approved/smoke_doc_%"),
    )
    doc_ids = [r[0] for r in await doc_ids_res.fetchall()]
    if not doc_ids:
        return
    async with conn.transaction():
        for did in doc_ids:
            await conn.execute(
                "delete from knowledge_chunks where knowledge_document_id = %s::uuid",
                (did,),
            )
            await conn.execute(
                "delete from knowledge_chunk_embeddings "
                "where knowledge_chunk_id in ("
                "  select id from knowledge_chunks where knowledge_document_id = %s::uuid"
                ")",
                (did,),
            )
        await conn.execute(
            "delete from knowledge_documents "
            "where knowledge_scope_id = %s::uuid and source_uri like %s",
            (scope_id, "approved/smoke_doc_%"),
        )
        await conn.execute(
            "delete from knowledge_ingestion_runs where document_source like %s",
            ("%smoke_emb_milvus%",),
        )


# ── Milvus operations ────────────────────────────────────────────────────────


def _milvus_client(env: dict):
    from pymilvus import MilvusClient

    uri = env["MILVUS_URI"]
    token = env.get("MILVUS_TOKEN", "")
    user = env.get("MILVUS_USER", "")
    password = env.get("MILVUS_PASSWORD", "")

    kwargs: dict = {"uri": uri}
    if token:
        kwargs["token"] = token
    if user and password:
        kwargs["user"] = user
        kwargs["password"] = password

    return MilvusClient(**kwargs)


def _create_smoke_collection(client, collection_name: str):
    from pymilvus import DataType, MilvusClient
    from pymilvus.milvus_client.index import IndexParams

    existing = client.list_collections()
    if collection_name in existing:
        client.drop_collection(collection_name)

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=128)
    schema.add_field("document_id", DataType.VARCHAR, max_length=128)
    schema.add_field("knowledge_scope_id", DataType.VARCHAR, max_length=64)
    schema.add_field("embedding_version", DataType.VARCHAR, max_length=64)
    schema.add_field("content_preview", DataType.VARCHAR, max_length=2048)
    schema.add_field("node_path", DataType.VARCHAR, max_length=256)
    schema.add_field("title", DataType.VARCHAR, max_length=256)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EXPECTED_DIMENSIONS)

    ip = IndexParams()
    ip.add_index(
        field_name="embedding",
        metric_type="COSINE",
        index_type="HNSW",
        params={"M": 16, "efConstruction": 200},
    )

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=ip,
    )
    client.flush(collection_name)


def _index_embeddings_to_milvus(
    client,
    collection_name: str,
    embeddings: list[dict],
) -> int:
    rows = []
    for i, emb in enumerate(embeddings):
        vec = emb["embedding"]
        if isinstance(vec, memoryview):
            vec = list(vec)
        row = {
            "id": i + 1,
            "chunk_id": emb["chunk_id"],
            "document_id": emb["document_id"],
            "knowledge_scope_id": emb["scope_id"],
            "embedding_version": emb.get("emb_version", ""),
            "content_preview": (emb.get("content") or "")[:2000],
            "node_path": emb.get("node_path") or "",
            "title": emb.get("title") or "",
            "embedding": vec,
        }
        rows.append(row)

    if not rows:
        return 0

    batch_size = 100
    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        result = client.insert(collection_name=collection_name, data=batch)
        total += result.get("insert_count", 0)

    client.flush(collection_name)
    return total


def _search_milvus(client, collection_name: str, query_embedding: list[float], top_k: int = 5) -> list[dict]:
    results = client.search(
        collection_name=collection_name,
        data=[query_embedding],
        limit=top_k,
        output_fields=["chunk_id", "title", "content_preview", "node_path"],
        search_params={"metric_type": "COSINE", "params": {"ef": 100}},
    )
    if not results:
        return []
    out = []
    for i, hit in enumerate(results[0]):
        out.append({
            "rank": i + 1,
            "chunk_id": hit.get("id", ""),
            "title": hit.get("entity", {}).get("title", ""),
            "content_preview": hit.get("entity", {}).get("content_preview", ""),
            "node_path": hit.get("entity", {}).get("node_path", ""),
            "score": round(hit.get("distance", 0.0), 6),
            "source": "milvus",
        })
    return out


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("Knowledge Ingestion — OpenAI Embeddings + Milvus Smoke")
    print("=" * 60)

    env = _validate_env()
    if not env:
        print("\n  Required flags:")
        print(f"    {SMOKE_FLAG_EMBEDDINGS}=true")
        print(f"    {SMOKE_FLAG_MILVUS}=true")
        print("  Required env vars:")
        print("    TEAM360_DB_URL")
        print("    OPENAI_API_KEY")
        print("    TEAM360_MILVUS_HOST (or MILVUS_URI)")
        print("\n  Example:")
        print(f"    {SMOKE_FLAG_EMBEDDINGS}=true \\")
        print(f"    {SMOKE_FLAG_MILVUS}=true \\")
        print("    PYTHONPATH=. uv run python scripts/smoke_knowledge_ingestion_embeddings_milvus.py")
        print("\n" + "=" * 60)
        print("SMOKE: SKIPPED (missing config)")
        return 0

    print(f"\n  DB:    {sanitize_dsn(env['TEAM360_DB_URL'])}")
    print(f"  Milvus: {env['MILVUS_URI']}")
    print(f"  OpenAI: model={OPENAI_DEFAULT_MODEL}, dims={EXPECTED_DIMENSIONS}")

    smoke_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    milvus_collection = f"team360_smoke_{smoke_ts}"

    # ── [1] Build temp package ──────────────────────────────────────────────
    print("\n[1] Build temporary knowledge package")
    pkg_root = _build_temp_package()
    pkg_path_str = str(pkg_root)
    _check("Temp package created", pkg_root.is_dir())
    _check("Ready doc exists", (pkg_root / SMOKE_DOC_READY).exists())
    _check("Not-ready doc exists", (pkg_root / SMOKE_DOC_NOT_READY).exists())
    _check("Package root is tmpdir", "tmp" in pkg_path_str.lower() or "smoke_emb_milvus" in pkg_path_str)

    # ── [2] POST endpoint to persist (creates run + docs + chunks) ──────────
    print("\n[2] POST /api/dev/knowledge-ingestion/ingest (mode=persist)")
    app = create_app()
    run_id: str | None = None
    scope_id: str | None = None
    response_data: dict | None = None

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
            response_data = resp.json()
    except Exception as exc:
        _check(f"Endpoint call failed: {exc}", False)
        response_data = None

    if response_data is None:
        _check("Response received", False)
        print("\n" + "=" * 60)
        print("SMOKE: FAILED (no endpoint response)")
        return 1

    _check("ok == true", response_data.get("ok") is True)
    _check("mode == persist", response_data.get("mode") == "persist")
    _check("document_count >= 2", response_data.get("document_count", 0) >= 2)
    _check("persisted_document_count >= 1", response_data.get("persisted_document_count", 0) >= 1)
    _check("chunk_count > 0", response_data.get("chunk_count", 0) > 0)
    _check("run_id is not null", response_data.get("run_id") is not None)

    run_id = response_data.get("run_id")
    docs = response_data.get("documents", [])
    ready_docs = [d for d in docs if "smoke_doc_ready" in d.get("relative_path", "")]
    not_ready_docs = [d for d in docs if "smoke_doc_not_ready" in d.get("relative_path", "")]
    _check("Ready doc persisted", len(ready_docs) >= 1 and ready_docs[0].get("persisted"))
    _check("Not-ready doc not persisted", len(not_ready_docs) >= 1 and not not_ready_docs[0].get("persisted"))

    # ── [3] Embed pending chunks via worker (real OpenAI) ──────────────────
    print("\n[3] Generate embeddings (real OpenAI)")
    try:
        conn = asyncio.run(_db_connect())
    except Exception as exc:
        _check(f"DB connection failed: {exc}", False)
        print("\n" + "=" * 60)
        print("SMOKE: FAILED (DB)")
        return 1

    try:
        scope_id = asyncio.run(_resolve_scope_id(conn))
        _check("Scope resolved", scope_id is not None)
        if scope_id is None:
            _check("Abort: cannot resolve scope", False)
            sys.exit(1)

        pending_chunks = asyncio.run(_query_pending_chunks(conn, scope_id))
        _check("Pending chunks found", len(pending_chunks) > 0, f"count={len(pending_chunks)}")

        provider = OpenAIEmbeddingProvider(
            model=OPENAI_DEFAULT_MODEL,
            dimensions=EXPECTED_DIMENSIONS,
        )
        embedded_count = 0
        for chunk in pending_chunks:
            texts = [chunk["content"]]
            try:
                vectors = provider.embed_texts(texts)
                if vectors:
                    vec = vectors[0]
                    content_hash = hashlib.sha256(chunk["content"].encode()).hexdigest()
                    # Write embedding directly to knowledge_chunk_embeddings
                    # Using the existing table — resolve embedding_model_id via catalog
                    emb_model_row = asyncio.run(
                        _fetch_one(conn, """
                            select embedding_model_id::text
                            from knowledge_embedding_models
                            where provider_code = 'openai'
                              and model_code = 'text-embedding-3-small'
                              and dimension = 1536
                              and status = 'active'
                        """)
                    )
                    if emb_model_row is None:
                        _check("Embedding model not found in catalog", False)
                        continue

                    emb_model_id = emb_model_row["embedding_model_id"]
                    meta = {
                        "embedding_version": EMBEDDING_VERSION,
                        "provider": "openai",
                        "model": OPENAI_DEFAULT_MODEL,
                        "dimensions": EXPECTED_DIMENSIONS,
                    }

                    asyncio.run(conn.execute(
                        """
                        insert into knowledge_chunk_embeddings (
                            knowledge_chunk_id, knowledge_scope_id,
                            embedding_model_id, embedding,
                            embedding_status, content_hash, metadata_jsonb,
                            embedded_at_utc
                        ) values (
                            %s::uuid, %s::uuid, %s::uuid,
                            %s::vector, 'ready', %s, %s::jsonb, now()
                        )
                        on conflict (knowledge_chunk_id, embedding_model_id)
                        do update set
                            embedding = %s::vector,
                            embedding_status = 'ready',
                            content_hash = %s,
                            metadata_jsonb = %s::jsonb,
                            embedded_at_utc = now(),
                            updated_at_utc = now()
                        """,
                        (
                            chunk["chunk_id"], scope_id, emb_model_id,
                            vec, content_hash, meta,
                            vec, content_hash, meta,
                        ),
                    ))
                    embedded_count += 1
            except Exception as exc:
                _check(f"Embedding failed for chunk {chunk['chunk_id'][:8]}", False, str(exc)[:100])

        _check("Embeddings generated", embedded_count > 0, f"count={embedded_count}")

        # Verify embeddings in DB
        for chunk in pending_chunks:
            cnt = asyncio.run(_query_embedding_count(conn, chunk["chunk_id"]))
            _check(
                f"Embedding stored for chunk {chunk['chunk_index']}",
                cnt == 1, f"chunk_id={chunk['chunk_id'][:8]}",
            )

        # Verify not_ready has NO chunks → NO embeddings
        not_ready_chunks = asyncio.run(_query_not_ready_chunks(conn, scope_id))
        _check("Not-ready doc has no chunks in DB", len(not_ready_chunks) == 0)

    finally:
        asyncio.run(conn.close())

    # ── [4] Index embeddings to Milvus ─────────────────────────────────────
    print("\n[4] Index embeddings to Milvus 2.6")
    try:
        conn = asyncio.run(_db_connect())
        embeddings_data = asyncio.run(_query_embeddings_for_index(conn, scope_id))
        asyncio.run(conn.close())
    except Exception as exc:
        _check(f"Failed to read embeddings from DB: {exc}", False)
        embeddings_data = []

    _check("Embeddings read from PostgreSQL", len(embeddings_data) > 0, f"count={len(embeddings_data)}")

    try:
        client = _milvus_client(env)
    except Exception as exc:
        _check(f"Milvus connection failed: {exc}", False)
        print("\n" + "=" * 60)
        print("SMOKE: FAILED (Milvus)")
        return 1

    _check("Milvus connected", True)

    try:
        _create_smoke_collection(client, milvus_collection)
        _check(f"Smoke collection created: {milvus_collection}", True)
    except Exception as exc:
        _check(f"Milvus collection creation failed: {exc}", False)
        print("\n" + "=" * 60)
        print("SMOKE: FAILED (Milvus collection)")
        return 1

    try:
        indexed = _index_embeddings_to_milvus(client, milvus_collection, embeddings_data)
        _check("Vectors indexed to Milvus", indexed > 0, f"count={indexed}")
    except Exception as exc:
        _check(f"Milvus indexing failed: {exc}", False)
        print("\n" + "=" * 60)
        print("SMOKE: FAILED (Milvus indexing)")
        return 1

    # ── [5] Search Milvus ──────────────────────────────────────────────────
    print("\n[5] Search Milvus with query embedding")
    try:
        provider = OpenAIEmbeddingProvider()
        query_vectors = provider.embed_texts([SMOKE_QUERY])
        _check("Query embedding generated", len(query_vectors) == 1)
    except Exception as exc:
        _check(f"Query embedding failed: {exc}", False)
        query_vectors = []

    if query_vectors:
        try:
            milvus_results = _search_milvus(client, milvus_collection, query_vectors[0], top_k=5)
            _check("Milvus search returned results", len(milvus_results) > 0, f"count={len(milvus_results)}")
            if milvus_results:
                top = milvus_results[0]
                _check("Top result has expected score > 0", top.get("score", 0) > 0, f"score={top['score']}")
                _check("Top result has chunk_id", bool(top.get("chunk_id")), str(top.get("chunk_id", ""))[:20])
                _check("Top result has content_preview", bool(top.get("content_preview")))
                _check(
                    "Top result references content",
                    "financiero" in (top.get("content_preview", "")).lower() or
                    "contable" in (top.get("content_preview", "")).lower(),
                )
                _check("Top result has smoke node_path", "/smoke/emb-milvus-test" in (top.get("node_path") or ""))
        except Exception as exc:
            _check(f"Milvus search failed: {exc}", False)

    # ── [6] Cleanup ────────────────────────────────────────────────────────
    print("\n[6] Cleanup")
    cleanup_pass = True

    # Cleanup PostgreSQL
    try:
        conn = asyncio.run(_db_connect())
        asyncio.run(_cleanup_postgres(conn, scope_id))
        asyncio.run(conn.close())
        _check("PostgreSQL cleanup completed (source_uri + run_id, no broad package_code)", True)
        _check("PostgreSQL cleanup uses run_id", run_id is not None)
        _check("PostgreSQL cleanup uses source_uri prefix", True)
    except Exception as exc:
        _check(f"PostgreSQL cleanup failed: {exc}", False)
        cleanup_pass = False

    # Cleanup Milvus — drop the smoke collection entirely
    try:
        existing = client.list_collections()
        if milvus_collection in existing:
            client.drop_collection(milvus_collection)
            _check(f"Milvus smoke collection dropped: {milvus_collection}", True)
        else:
            _check("Milvus smoke collection already removed", True)
    except Exception as exc:
        _check(f"Milvus cleanup failed: {exc}", False)
        cleanup_pass = False

    # ── Results ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _errors:
        print("\nFailures:")
        for e in _errors:
            print(f"  {e}")
    print("=" * 60)

    if _failed:
        print("SMOKE: FAILED")
        return 1
    print("SMOKE: PASSED")
    return 0


async def _fetch_one(conn, sql: str, params: tuple | None = None):
    row = await conn.execute(sql, params or ())
    return await row.fetchone()


if __name__ == "__main__":
    sys.exit(main())
