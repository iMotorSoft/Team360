"""Smoke for Fase 1.6 — Sales Diagnosis Runtime dev/debug con retrieval real
desde Knowledge Ingestion (PostgreSQL + pgvector).

Requiere:

  TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=knowledge_ingestion
  TEAM360_DB_URL (o TEAM360_DB_URL_PSQL o DB_PG_V360_URL)
  OPENAI_API_KEY (o OpenAI_Key_JAI_query)

Opcional:
  TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS=true  (si faltan embeddings)

Usage:
  cd SrvRestAstroLS_v1/backend
  TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=knowledge_ingestion \
  PYTHONPATH=. uv run python scripts/smoke_sales_diagnosis_runtime_dev_knowledge_ingestion_retrieval.py

Expected: ALL PASSED (exit 0)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.automation_diagnosis.knowledge_retrieval_provider import (
    DEV_RETRIEVAL_ENV,
    DEV_RETRIEVAL_VALUE,
    KnowledgeIngestionSalesDiagnosisRetrievalProvider,
)
from modules.automation_diagnosis.schemas import RetrievedContext
from modules.db.settings import get_database_settings, sanitize_dsn
from modules.knowledge_ingestion.embedding_provider import (
    EMBEDDING_VERSION,
    EXPECTED_DIMENSIONS,
    OPENAI_DEFAULT_MODEL,
    OpenAIEmbeddingProvider,
)

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

SCOPE_ORG = "team360_live"
SCOPE_WS = "team360_public_site"
SCOPE_KS = "ks_team360_sales_diagnosis"
SCOPE_PKG = "pkg_sales_diagnosis"

DIAGNOSTIC_QUERIES = [
    ("WhatsApp automation", "Quiero automatizar consultas por WhatsApp, se puede"),
    ("QR / diagnostic_code", "Team360 puede pedir codigos o QR por mi"),
    ("Pricing / auto-quote", "Puede cotizar automaticamente"),
    ("MFA / aprobacion manual", "Que pasa si una app requiere MFA o aprobacion manual"),
    ("SAP Business One", "Pueden integrarse con SAP Business One"),
]


def _validate_env() -> dict[str, str]:
    errors: list[str] = []
    env: dict[str, str] = {}

    ret_val = os.environ.get(DEV_RETRIEVAL_ENV, "").strip().lower()
    if ret_val != DEV_RETRIEVAL_VALUE:
        errors.append(
            f"{DEV_RETRIEVAL_ENV}={DEV_RETRIEVAL_VALUE} is required"
        )
    else:
        env["DEV_MODE"] = ret_val

    db_url = (
        os.environ.get("TEAM360_DB_URL")
        or os.environ.get("TEAM360_DB_URL_PSQL")
        or os.environ.get("DB_PG_V360_URL")
    )
    if not db_url:
        errors.append("TEAM360_DB_URL (or equivalent) is required")
    else:
        env["DB_URL"] = db_url

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        errors.append("OPENAI_API_KEY is required")
    else:
        env["OPENAI_KEY"] = _sanitize(api_key)

    if errors:
        print("\n  Missing required environment:")
        for e in errors:
            print(f"    - {e}")
        print()
        return {}

    return env


# ── Preflight: validate DB, embeddings, scope ──────────────────────────────


def run_preflight(provider: KnowledgeIngestionSalesDiagnosisRetrievalProvider) -> bool:
    print("\n[PREFLIGHT]")
    ok = True

    # 1. DB accessible
    try:
        settings = get_database_settings()
        import psycopg
        conn = psycopg.connect(settings.dsn, connect_timeout=5)
        _check("PostgreSQL accessible", True, sanitize_dsn(settings.dsn))
        conn.close()
    except Exception as exc:
        _check(f"PostgreSQL connection failed: {exc}", False)
        return False

    # 2. PostgreSQL tiene datos de knowledge_scope
    try:
        conn = psycopg.connect(settings.dsn, connect_timeout=5)
        row = conn.execute(
            "select id::text from knowledge_scopes where scope_code = %s",
            (SCOPE_KS,),
        ).fetchone()
        if row:
            _check("Knowledge scope exists in DB", True, f"{SCOPE_KS} -> {row[0][:8]}...")
        else:
            _check("Knowledge scope NOT found in DB", False, SCOPE_KS)
            ok = False
            conn.close()
            return False
        conn.close()
    except Exception as exc:
        _check(f"Scope query failed: {exc}", False)
        return False

    # 3. Hay chunks embeddizados
    try:
        conn = psycopg.connect(settings.dsn, connect_timeout=5)
        scope_row = conn.execute(
            "select id::text from knowledge_scopes where scope_code = %s",
            (SCOPE_KS,),
        ).fetchone()
        db_scope_id = scope_row[0] if scope_row else None
        if db_scope_id:
            count_row = conn.execute(
                "select count(*) from knowledge_chunk_embeddings "
                "where knowledge_scope_id = %s::uuid and embedding_status = 'ready'",
                (db_scope_id,),
            ).fetchone()
            emb_count = count_row[0] if count_row else 0
            _check("Embeddings exist in PostgreSQL", emb_count > 0, f"count={emb_count}")
            if emb_count == 0:
                ok = False
        conn.close()
    except Exception as exc:
        _check(f"Embedding count query failed: {exc}", False)
        ok = False

    # 4. Provider se construye correctamente
    _check("Provider constructed", provider is not None)
    if provider is None:
        return False

    # 5. scope_debug funciona
    debug_info = provider.scope_debug(SCOPE_KS)
    has_error = "error" in debug_info
    _check("scope_debug sin errores", not has_error, debug_info.get("error", ""))
    if has_error:
        ok = False

    # 6. No dev_doc_* sources en la coleccion
    try:
        conn = psycopg.connect(settings.dsn, connect_timeout=5)
        dev_row = conn.execute(
            "select count(*) from knowledge_documents kd "
            "join knowledge_scopes ks on ks.id = kd.knowledge_scope_id "
            "where ks.scope_code = %s and kd.source_uri like 'dev_doc_%%'",
            (SCOPE_KS,),
        ).fetchone()
        dev_count = dev_row[0] if dev_row else 0
        _check("No dev_doc_* sources in scope", dev_count == 0, f"found {dev_count}")
        if dev_count > 0:
            ok = False
        conn.close()
    except Exception as exc:
        _check(f"dev_doc check failed: {exc}", False)

    return ok


# ── Smoke test: queries reales contra retrieval real ───────────────────────


def run_retrieval_smoke(provider: KnowledgeIngestionSalesDiagnosisRetrievalProvider) -> bool:
    print("\n[RETRIEVAL SMOKE]")
    ok = True

    for label, query_text in DIAGNOSTIC_QUERIES:
        print(f"\n  Query [{label}]: {query_text[:60]}...")
        if not provider:
            _check("Provider not available", False)
            continue

        try:
            start = time.time()
            result = provider.search(SCOPE_KS, query_text, "rag", top_k=5)
            elapsed = int((time.time() - start) * 1000)
        except Exception as exc:
            _check(f"Search threw exception: {exc}", False)
            ok = False
            continue

        is_retrieved_context = isinstance(result, RetrievedContext)
        _check("Returns RetrievedContext", is_retrieved_context)
        if not is_retrieved_context:
            ok = False
            continue

        _check("knowledge_scope_id set", bool(result.knowledge_scope_id))
        _check("query preserved", result.query == query_text)

        chunks = result.chunks
        _check("sources > 0", len(chunks) > 0, f"count={len(chunks)}")
        if not chunks:
            ok = False
            continue

        _check("top_k limit respected", len(chunks) <= 5, f"count={len(chunks)}")

        top = chunks[0]
        _check("title not empty", bool(top.get("title")), str(top.get("title", ""))[:50])
        _check("chunk_id not empty", bool(top.get("chunk_id")), str(top.get("chunk_id", ""))[:20])
        _check("score > 0", top.get("score", 0) > 0, f"score={top.get('score', 0)}")
        _check("content not empty", bool(top.get("content")), f"len={len(top.get('content', ''))}")

        meta = top.get("metadata") or {}
        has_source_uri = bool(meta.get("source_uri"))
        has_node_path = bool(meta.get("node_path"))
        _check("metadata.source_uri present", has_source_uri, meta.get("source_uri", "")[:60])
        _check("metadata.node_path present", has_node_path, meta.get("node_path", "")[:60])
        if not has_source_uri or not has_node_path:
            ok = False

        has_dev_doc = "dev_doc_" in (meta.get("source_uri", "") or "")
        _check("no dev_doc_* sources", not has_dev_doc)
        if has_dev_doc:
            ok = False

    return ok


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("Sales Diagnosis Runtime — Knowledge Ingestion Retrieval Smoke")
    print("Fase 1.6 — Dev/Debug")
    print("=" * 60)

    env = _validate_env()
    if not env:
        print("\n  Required env:")
        print(f"    {DEV_RETRIEVAL_ENV}={DEV_RETRIEVAL_VALUE}")
        print("    TEAM360_DB_URL")
        print("    OPENAI_API_KEY")
        print()
        print("=" * 60)
        print("SMOKE: SKIPPED (missing config)")
        return 0

    provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider(
        organization_code=SCOPE_ORG,
        workspace_code=SCOPE_WS,
        knowledge_scope_code=SCOPE_KS,
        package_code=SCOPE_PKG,
    )

    preflight_ok = run_preflight(provider)
    if not preflight_ok:
        print("\n  PREFLIGHT FAILED — no se ejecutaran queries de retrieval.")
        print("  Asegurar: PostgreSQL activo, scope existe, embeddings generados.")
        print()
        print("=" * 60)
        print("SMOKE: FAILED (preflight)")
        return 1

    retrieval_ok = run_retrieval_smoke(provider)

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


if __name__ == "__main__":
    sys.exit(main())
