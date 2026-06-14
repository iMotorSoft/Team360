"""Sales Diagnosis Knowledge Base Debug — backend-only.

Runs controlled steps against the real knowledge base to debug retrieval:
  --scan:            scan package (no external services)
  --persist:         persist docs + chunks to PostgreSQL
  --embed:           generate embeddings (requires OpenAI)
  --milvus-index:    index embeddings to Milvus
  --retrieve-debug:  run diagnostic queries against retrieval
  --all:             all steps above

Usage examples:
  # Scan only (no DB, no OpenAI, no Milvus)
  PYTHONPATH=. uv run python scripts/run_sales_diagnosis_knowledge_base_debug.py --scan

  # Full pipeline with all env vars
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS=true \
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS=true \
  PYTHONPATH=. uv run python scripts/run_sales_diagnosis_knowledge_base_debug.py --all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from litestar.testing import TestClient
from app import create_app
from modules.db.settings import get_database_settings, sanitize_dsn
from modules.knowledge_ingestion.embedding_provider import (
    EMBEDDING_VERSION,
    EXPECTED_DIMENSIONS,
    OPENAI_DEFAULT_MODEL,
    OpenAIEmbeddingProvider,
)
from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.schemas import (
    PackageScanRequest,
    check_document_ingestion_readiness,
)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_PACKAGE_CODE = "pkg_sales_diagnosis"
DEFAULT_SCOPE_CODE = "ks_team360_sales_diagnosis"
DEFAULT_ORG_CODE = "team360_live"
DEFAULT_WS_CODE = "team360_public_site"

SHARED_KNOWLEDGE_ROOT = (
    Path(__file__).resolve().parents[2] / "knowledge" / "packages" / DEFAULT_PACKAGE_CODE
)

DIAGNOSTIC_QUERIES = [
    "Quiero automatizar consultas por WhatsApp, se puede",
    "Team360 puede pedir codigos o QR por mi",
    "Ya tienen Step-to-Action listo",
    "Pueden integrarse con CRM y WhatsApp",
    "Que datos minimos necesita Vera para diagnosticar",
    "Puede cotizar automaticamente",
    "Que pasa si una app requiere MFA o aprobacion manual",
    "Como diferenciar automatizable de vendible hoy",
]

REQUIRED_EMBEDDINGS_FLAG = "TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS"
REQUIRED_MILVUS_FLAG = "TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS"

TMP_DIR = Path(__file__).resolve().parent.parent / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = TMP_DIR / "sales_diagnosis_knowledge_debug_report.json"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _log(msg: str):
    print(f"  {msg}")


def _step(title: str):
    print(f"\n{'='*60}")
    print(f"[{title}]")
    print(f"{'='*60}")


def _check_env(var: str, label: str) -> bool:
    val = os.environ.get(var, "")
    if not val:
        print(f"  SKIP  {label}: {var} not set")
        return False
    return True


# ── Step 1: Scan ─────────────────────────────────────────────────────────────


def step_scan(package_code: str, package_root: str) -> dict:
    _step("SCAN")
    scanner = KnowledgePackageScanner()
    request = PackageScanRequest(
        package_code=package_code,
        package_root=package_root,
        dry_run=True,
        include_drafts=False,
    )
    result = scanner.scan(request)
    print(f"  Scanned: {result.scanned_count} files")
    print(f"  Valid:   {result.valid_count}")
    print(f"  Invalid: {result.invalid_count}")
    print(f"  Candidates: {result.candidate_count}")
    print(f"  Skipped: {result.skipped_count}")
    for doc in result.documents:
        status = "READY" if doc.candidate_for_ingestion else "SKIP"
        print(f"    [{status}] {doc.relative_path}")
        if doc.issues:
            for iss in doc.issues:
                print(f"      - [{iss.severity}] {iss.message}")
    return {
        "scanned_count": result.scanned_count,
        "valid_count": result.valid_count,
        "invalid_count": result.invalid_count,
        "candidate_count": result.candidate_count,
        "skipped_count": result.skipped_count,
        "documents": [
            {
                "relative_path": d.relative_path,
                "valid": d.valid,
                "candidate": d.candidate_for_ingestion,
                "issues": [{"severity": i.severity, "message": i.message} for i in d.issues],
            }
            for d in result.documents
        ],
        "warnings": result.warnings,
        "errors": result.errors,
    }


# ── Step 2: Persist ──────────────────────────────────────────────────────────


def step_persist(package_code: str, package_root: str, org_code: str, ws_code: str, ks_code: str) -> dict:
    _step("PERSIST")
    try:
        settings = get_database_settings()
    except Exception as exc:
        print(f"  SKIP  DB not configured: {exc}")
        return {"error": str(exc)}
    from psycopg import AsyncConnection

    result_data: dict = {}

    async def _run():
        nonlocal result_data
        conn = await AsyncConnection.connect(settings.dsn, connect_timeout=5)
        try:
            app = create_app()
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/api/dev/knowledge-ingestion/ingest",
                    json={
                        "package_code": package_code,
                        "package_path": package_root,
                        "mode": "persist",
                        "include_drafts": False,
                        "chunking_strategy": "markdown",
                        "organization_code": org_code,
                        "workspace_code": ws_code,
                        "knowledge_scope_code": ks_code,
                    },
                )
                data = resp.json()
                print(f"  HTTP {resp.status_code}")
                print(f"  ok: {data.get('ok')}")
                print(f"  documents: {data.get('document_count', 0)}")
                print(f"  persisted: {data.get('persisted_document_count', 0)}")
                print(f"  chunks: {data.get('chunk_count', 0)}")
                print(f"  run_id: {data.get('run_id')}")
                scopes = data.get("scope_errors", [])
                if scopes:
                    print(f"  scope_errors: {scopes}")
                result_data = data
        finally:
            await conn.close()

    import asyncio
    asyncio.run(_run())
    return result_data


# ── Step 3: Embed ────────────────────────────────────────────────────────────


def step_embed(package_code: str, ks_code: str) -> dict:
    _step("EMBED")
    if not _check_env("OPENAI_API_KEY", "OpenAI"):
        return {"error": "OPENAI_API_KEY not set"}
    if os.environ.get(REQUIRED_EMBEDDINGS_FLAG, "").lower() != "true":
        print(f"  SKIP  {REQUIRED_EMBEDDINGS_FLAG}=true required")
        return {"error": f"{REQUIRED_EMBEDDINGS_FLAG}=true required"}
    from psycopg import AsyncConnection

    settings = get_database_settings()
    provider = OpenAIEmbeddingProvider()
    embedded_count = 0
    errors: list[str] = []

    async def _run():
        nonlocal embedded_count
        conn = await AsyncConnection.connect(settings.dsn, connect_timeout=5)
        try:
            scope_row = await conn.execute(
                "select id::text from knowledge_scopes where scope_code = %s",
                (ks_code,),
            )
            r = await scope_row.fetchone()
            if r is None:
                print(f"  Scope {ks_code} not found")
                return
            scope_id = r[0]
            emb_row = await conn.execute(
                "select embedding_model_id::text from knowledge_embedding_models "
                "where provider_code = 'openai' and model_code = 'text-embedding-3-small' "
                "and dimension = 1536 and status = 'active'"
            )
            emb_r = await emb_row.fetchone()
            if emb_r is None:
                print("  Embedding model not found in catalog")
                return
            emb_model_id = emb_r[0]
            pending = await conn.execute(
                """
                select kc.id::text as chunk_id, kc.content,
                       kd.knowledge_scope_id::text as scope_id
                from knowledge_chunks kc
                join knowledge_documents kd on kd.id = kc.knowledge_document_id
                where kd.knowledge_scope_id = %s::uuid
                  and kc.id not in (
                      select knowledge_chunk_id from knowledge_chunk_embeddings
                      where embedding_status = 'ready'
                  )
                """,
                (scope_id,),
            )
            chunks = await pending.fetchall()
            print(f"  Pending chunks to embed: {len(chunks)}")
            for chunk in chunks:
                chunk_id = chunk["chunk_id"]
                content = chunk["content"]
                scope_id_val = chunk["scope_id"]
                try:
                    vec = provider.embed_texts([content])[0]
                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    meta = json.dumps({
                        "embedding_version": EMBEDDING_VERSION,
                        "provider": "openai",
                        "model": OPENAI_DEFAULT_MODEL,
                        "dimensions": EXPECTED_DIMENSIONS,
                    })
                    await conn.execute(
                        """
                        insert into knowledge_chunk_embeddings (
                            knowledge_chunk_id, knowledge_scope_id,
                            embedding_model_id, embedding,
                            embedding_status, content_hash, metadata_jsonb,
                            embedded_at_utc
                        ) values (%s::uuid, %s::uuid, %s::uuid, %s::vector,
                                  'ready', %s, %s::jsonb, now())
                        on conflict (knowledge_chunk_id, embedding_model_id)
                        do update set embedding = %s::vector,
                            embedding_status = 'ready', content_hash = %s,
                            metadata_jsonb = %s::jsonb, embedded_at_utc = now(),
                            updated_at_utc = now()
                        """,
                        (chunk_id, scope_id_val, emb_model_id, vec,
                         content_hash, meta, vec, content_hash, meta),
                    )
                    embedded_count += 1
                except Exception as exc:
                    errors.append(f"chunk {chunk_id[:8]}: {exc}")
        finally:
            await conn.close()

    import asyncio
    asyncio.run(_run())
    print(f"  Embedded: {embedded_count}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for e in errors[:5]:
            print(f"    - {e}")
    return {"embedded_count": embedded_count, "errors": errors}


# ── Step 4: Milvus index ──────────────────────────────────────────────────────


def step_milvus_index(ks_code: str) -> dict:
    _step("MILVUS INDEX")
    if os.environ.get(REQUIRED_MILVUS_FLAG, "").lower() != "true":
        print(f"  SKIP  {REQUIRED_MILVUS_FLAG}=true required")
        return {"error": f"{REQUIRED_MILVUS_FLAG}=true required"}
    milvus_uri = os.environ.get("MILVUS_URI") or (
        f"http://{os.environ.get('TEAM360_MILVUS_HOST', 'localhost')}"
        f":{os.environ.get('TEAM360_MILVUS_PORT', '19530')}"
    )
    if not milvus_uri:
        print("  SKIP  No Milvus URI configured")
        return {"error": "No Milvus URI"}

    from pymilvus import DataType, MilvusClient
    from pymilvus.milvus_client.index import IndexParams
    from psycopg import AsyncConnection

    settings = get_database_settings()
    coll_name = f"team360_diagnosis_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    indexed = 0
    errors: list[str] = []

    async def _fetch():
        nonlocal indexed
        conn = await AsyncConnection.connect(settings.dsn, connect_timeout=5)
        try:
            rows = await conn.execute(
                """
                select kce.embedding, kc.id::text as chunk_id,
                       kc.knowledge_document_id::text as document_id,
                       kd.knowledge_scope_id::text as scope_id,
                       kc.title, kc.content, kc.node_path,
                       kce.metadata_jsonb->>'embedding_version' as emb_version
                from knowledge_chunk_embeddings kce
                join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
                join knowledge_documents kd on kd.id = kc.knowledge_document_id
                join knowledge_scopes ks on ks.id = kd.knowledge_scope_id
                where ks.scope_code = %s
                  and kce.embedding_status = 'ready'
                  and kce.embedding is not null
                """,
                (ks_code,),
            )
            embs = await rows.fetchall()
            print(f"  Embeddings to index: {len(embs)}")
            if not embs:
                return
            client = MilvusClient(uri=milvus_uri)
            existing = client.list_collections()
            if coll_name in existing:
                client.drop_collection(coll_name)
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
            ip.add_index(field_name="embedding", metric_type="COSINE", index_type="HNSW",
                         params={"M": 16, "efConstruction": 200})
            client.create_collection(collection_name=coll_name, schema=schema, index_params=ip)
            for i, emb in enumerate(embs):
                vec = emb["embedding"]
                if isinstance(vec, memoryview):
                    vec = list(vec)
                client.insert(coll_name, [{
                    "id": i + 1,
                    "chunk_id": emb["chunk_id"],
                    "document_id": emb["document_id"],
                    "knowledge_scope_id": emb["scope_id"],
                    "embedding_version": emb.get("emb_version") or "",
                    "content_preview": (emb.get("content") or "")[:2000],
                    "node_path": emb.get("node_path") or "",
                    "title": emb.get("title") or "",
                    "embedding": vec,
                }])
                indexed += 1
            client.flush(coll_name)
        finally:
            await conn.close()

    import asyncio
    asyncio.run(_fetch())
    print(f"  Indexed to Milvus: {indexed} vectors")
    print(f"  Collection: {coll_name}")
    return {"indexed": indexed, "collection": coll_name, "errors": errors}


# ── Step 5: Retrieve debug ──────────────────────────────────────────────────


def step_retrieve_debug(ks_code: str, top_k: int = 5) -> dict:
    _step("RETRIEVE DEBUG")
    if not _check_env("OPENAI_API_KEY", "OpenAI"):
        return {"error": "OPENAI_API_KEY not set"}
    settings = get_database_settings()
    provider = OpenAIEmbeddingProvider()
    results_data: list[dict] = []

    async def _run():
        nonlocal results_data
        from psycopg import AsyncConnection
        conn = await AsyncConnection.connect(settings.dsn, connect_timeout=5)
        try:
            for query in DIAGNOSTIC_QUERIES:
                print(f"\n  Query: {query}")
                try:
                    vec = provider.embed_texts([query])[0]
                except Exception as exc:
                    print(f"    SKIP embedding error: {exc}")
                    results_data.append({"query": query, "error": str(exc)})
                    continue
                rows = await conn.execute(
                    """
                    select
                        kc.id::text as chunk_id,
                        kd.source_uri,
                        kc.title,
                        kc.node_path,
                        kc.chunk_index,
                        kc.content,
                        kc.metadata_jsonb,
                        kce.metadata_jsonb as emb_meta,
                        1 - (kce.embedding <=> %s::vector) as score
                    from knowledge_chunk_embeddings kce
                    join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
                    join knowledge_documents kd on kd.id = kc.knowledge_document_id
                    join knowledge_scopes ks on ks.id = kd.knowledge_scope_id
                    where ks.scope_code = %s
                      and kce.embedding_status = 'ready'
                      and kce.embedding is not null
                    order by kce.embedding <=> %s::vector
                    limit %s
                    """,
                    (vec, ks_code, vec, top_k),
                )
                hits = await rows.fetchall()
                print(f"    Results: {len(hits)}")
                query_results: list[dict] = []
                for hit in hits:
                    meta = hit.get("metadata_jsonb") or {}
                    emb_meta = hit.get("emb_meta") or {}
                    area_key = meta.get("area_key", "")
                    topic_key = meta.get("topic_key", "")
                    access_tags = meta.get("access_tags", [])
                    risk = meta.get("risk_level", "")
                    planned_ext = meta.get("step_to_action_status", "") == "planned_extension"
                    security_hitl = "human_review_required" in str(meta.get("offer_decision", ""))
                    signal_notes = []
                    if planned_ext:
                        signal_notes.append("planned_extension")
                    if security_hitl:
                        signal_notes.append("human_review_required")
                    content_preview = (hit.get("content") or "")[:300]
                    score = round(float(hit["score"]), 6) if hit.get("score") is not None else 0.0
                    print(f"      [{score:.4f}] {hit.get('source_uri', '?')} / {hit.get('title', '?')[:50]}")
                    if signal_notes:
                        print(f"        signals: {', '.join(signal_notes)}")
                    query_results.append({
                        "chunk_id": hit["chunk_id"],
                        "source_uri": hit.get("source_uri", ""),
                        "title": hit.get("title", ""),
                        "node_path": hit.get("node_path", ""),
                        "chunk_index": hit.get("chunk_index", 0),
                        "area_key": area_key,
                        "topic_key": topic_key,
                        "access_tags": access_tags,
                        "score": score,
                        "content_preview": content_preview,
                        "signals": signal_notes,
                        "risk_level": risk,
                    })
                results_data.append({
                    "query": query,
                    "top_k": top_k,
                    "results": query_results,
                })
        finally:
            await conn.close()

    import asyncio
    asyncio.run(_run())

    report = {
        "generated_at": datetime.now().isoformat(),
        "knowledge_scope_code": ks_code,
        "top_k": top_k,
        "queries": results_data,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  Report saved: {REPORT_PATH}")
    return report


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Sales Diagnosis Knowledge Base Debug"
    )
    parser.add_argument("--scan", action="store_true", help="Scan package")
    parser.add_argument("--persist", action="store_true", help="Persist to PostgreSQL")
    parser.add_argument("--embed", action="store_true", help="Generate embeddings")
    parser.add_argument("--milvus-index", action="store_true", help="Index to Milvus")
    parser.add_argument("--retrieve-debug", action="store_true", help="Run retrieval debug")
    parser.add_argument("--all", action="store_true", help="Run all steps")
    parser.add_argument("--package-code", default=DEFAULT_PACKAGE_CODE)
    parser.add_argument("--package-path", default="")
    parser.add_argument("--knowledge-scope-code", default=DEFAULT_SCOPE_CODE)
    parser.add_argument("--organization-code", default=DEFAULT_ORG_CODE)
    parser.add_argument("--workspace-code", default=DEFAULT_WS_CODE)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if not any([args.scan, args.persist, args.embed, args.milvus_index, args.retrieve_debug, args.all]):
        parser.print_help()
        return 0

    pkg_path = args.package_path or str(SHARED_KNOWLEDGE_ROOT)
    pkg_code = args.package_code

    if args.all:
        args.scan = args.persist = args.embed = args.milvus_index = args.retrieve_debug = True

    results: dict[str, dict] = {}

    if args.scan:
        results["scan"] = step_scan(pkg_code, pkg_path)

    if args.persist:
        results["persist"] = step_persist(
            pkg_code, pkg_path,
            args.organization_code, args.workspace_code, args.knowledge_scope_code,
        )

    if args.embed:
        results["embed"] = step_embed(pkg_code, args.knowledge_scope_code)

    if args.milvus_index:
        results["milvus_index"] = step_milvus_index(args.knowledge_scope_code)

    if args.retrieve_debug:
        results["retrieve_debug"] = step_retrieve_debug(args.knowledge_scope_code, args.top_k)

    json_results = json.dumps(results, indent=2, default=str)
    (TMP_DIR / "sales_diagnosis_debug_last_run.json").write_text(json_results, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
