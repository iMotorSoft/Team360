"""Index PostgreSQL knowledge embeddings into a production Milvus 2.6 collection
for Sales Diagnosis retrieval.

Creates collection: team360_sales_diagnosis_knowledge_v1 (or configured name)
Dimensions: 1536 (OpenAI text-embedding-3-small)

Usage:
  cd SrvRestAstroLS_v1/backend
  PYTHONPATH=. uv run python scripts/index_sales_diagnosis_milvus_production.py

Optional env vars:
  TEAM360_MILVUS_COLLECTION   (default: team360_sales_diagnosis_knowledge_v1)
  TEAM360_MILVUS_HOST         (default: localhost)
  TEAM360_MILVUS_PORT         (default: 19530)
  TEAM360_MILVUS_TOKEN        (optional)
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.db.settings import get_database_settings, sanitize_dsn
from psycopg import AsyncConnection

COLLECTION_NAME = os.environ.get(
    "TEAM360_MILVUS_COLLECTION", "team360_sales_diagnosis_knowledge_v1"
)
SCOPE_CODE = "ks_team360_sales_diagnosis"
EMBEDDING_DIM = 1536

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


async def _fetch_embeddings(conn, scope_uuid: str) -> list[dict]:
    rows = await conn.execute(
        """
        select
            kce.chunk_embedding_id::text as chunk_embedding_id,
            kc.id::text as chunk_id,
            kc.knowledge_document_id::text as document_id,
            kd.source_uri,
            kd.knowledge_scope_id::text as scope_id,
            kc.title,
            kc.content,
            kc.node_path,
            kc.chunk_index,
            kce.embedding,
            kce.metadata_jsonb->>'embedding_version' as embedding_version,
            kc.metadata_jsonb as chunk_metadata
        from knowledge_chunk_embeddings kce
        join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
        join knowledge_documents kd on kd.id = kc.knowledge_document_id
        where kd.knowledge_scope_id = %s::uuid
          and kce.embedding_status = 'ready'
          and kce.embedding is not null
        order by kc.chunk_index
        """,
        (scope_uuid,),
    )
    raw = await rows.fetchall() or []
    # Convert tuples to dicts using column names
    col_names = [desc[0] for desc in rows.description]
    return [dict(zip(col_names, row)) for row in raw]


def _create_collection(client, collection_name: str):
    from pymilvus import DataType, MilvusClient
    from pymilvus.milvus_client.index import IndexParams

    existing = client.list_collections()
    if collection_name in existing:
        _check(f"Collection already exists: {collection_name}", True)
        return

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=128, is_primary=True)
    schema.add_field("document_id", DataType.VARCHAR, max_length=128)
    schema.add_field("knowledge_scope_id", DataType.VARCHAR, max_length=64)
    schema.add_field("source_uri", DataType.VARCHAR, max_length=512)
    schema.add_field("title", DataType.VARCHAR, max_length=256)
    schema.add_field("node_path", DataType.VARCHAR, max_length=256)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("content_preview", DataType.VARCHAR, max_length=2048)
    schema.add_field("content", DataType.VARCHAR, max_length=65535)
    schema.add_field("embedding_version", DataType.VARCHAR, max_length=64)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)

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
    _check(f"Collection created: {collection_name}", True)


def _index_embeddings(client, collection_name: str, embeddings: list[dict]) -> int:
    rows = []
    for emb in embeddings:
        vec = emb["embedding"]
        if isinstance(vec, memoryview):
            vec = list(vec)
        elif isinstance(vec, str):
            import ast
            vec = ast.literal_eval(vec)

        content = emb.get("content") or ""
        rows.append({
            "chunk_id": emb["chunk_id"],
            "document_id": emb["document_id"],
            "knowledge_scope_id": emb["scope_id"],
            "source_uri": emb.get("source_uri") or "",
            "title": emb.get("title") or "",
            "node_path": emb.get("node_path") or "",
            "chunk_index": emb.get("chunk_index") or 0,
            "content_preview": content[:2000],
            "content": content,
            "embedding_version": emb.get("embedding_version") or "",
            "embedding": vec,
        })

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


def main() -> int:
    print("=" * 60)
    print("Index PostgreSQL → Milvus 2.6 — Production Collection")
    print("=" * 60)
    print(f"\n  Collection: {COLLECTION_NAME}")
    print(f"  Scope:      {SCOPE_CODE}")
    print(f"  Dimensions: {EMBEDDING_DIM}")

    # [1] Connect PostgreSQL
    print("\n[1] PostgreSQL")
    settings = get_database_settings()
    print(f"  DSN: {sanitize_dsn(settings.dsn)}")

    try:
        import asyncio
        conn = asyncio.run(AsyncConnection.connect(settings.dsn, connect_timeout=5))
        _check("Connected", True)
    except Exception as exc:
        _check(f"PostgreSQL: {exc}", False)
        return 1

    # [2] Resolve scope
    print("\n[2] Resolve scope")
    scope_row = asyncio.run(conn.execute(
        "select id::text from knowledge_scopes where scope_code = %s",
        (SCOPE_CODE,),
    ))
    scope_data = asyncio.run(scope_row.fetchone())
    if not scope_data:
        _check(f"Scope not found: {SCOPE_CODE}", False)
        return 1
    scope_uuid = scope_data[0]
    _check(f"Scope: {SCOPE_CODE} -> {scope_uuid[:8]}...", True)

    # [3] Fetch embeddings from PostgreSQL
    print("\n[3] Fetch embeddings")
    embeddings_data = asyncio.run(_fetch_embeddings(conn, scope_uuid))
    _check(f"Embeddings fetched", len(embeddings_data) > 0, f"count={len(embeddings_data)}")
    asyncio.run(conn.close())

    # [4] Connect Milvus
    print("\n[4] Milvus 2.6")
    milvus_uri = (
        os.environ.get("TEAM360_MILVUS_URI")
        or f"http://{os.environ.get('TEAM360_MILVUS_HOST', 'localhost')}:{os.environ.get('TEAM360_MILVUS_PORT', '19530')}"
    )
    safe_uri = milvus_uri.split("@")[-1] if "@" in milvus_uri else milvus_uri
    print(f"  URI: {safe_uri}")

    from pymilvus import MilvusClient
    milvus_kwargs: dict = {"uri": milvus_uri}
    token = os.environ.get("TEAM360_MILVUS_TOKEN") or ""
    if token:
        milvus_kwargs["token"] = token

    try:
        client = MilvusClient(**milvus_kwargs)
        _check("Connected", True)
    except Exception as exc:
        _check(f"Milvus: {exc}", False)
        return 1

    # [5] Create collection
    print(f"\n[5] Collection: {COLLECTION_NAME}")
    _create_collection(client, COLLECTION_NAME)

    # [6] Index
    print(f"\n[6] Index {len(embeddings_data)} vectors")
    ts = time.time()
    indexed = _index_embeddings(client, COLLECTION_NAME, embeddings_data)
    elapsed = int((time.time() - ts) * 1000)
    _check("Vectors indexed", indexed > 0, f"count={indexed} in {elapsed}ms")
    _check("All embeddings indexed", indexed == len(embeddings_data),
           f"{indexed}/{len(embeddings_data)}")

    # [7] Verify
    print("\n[7] Verify")
    stats = client.get_collection_stats(COLLECTION_NAME)
    row_count = stats.get("row_count", 0)
    _check(f"Collection has {row_count} rows", row_count == len(embeddings_data))

    # Results
    print("\n" + "=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _errors:
        for e in _errors:
            print(f"  {e}")
    print("=" * 60)
    if _failed:
        print("INDEX: FAILED")
        return 1
    print("INDEX: PASSED")
    return 0


if __name__ == "__main__":
    main()
