#!/usr/bin/env python3
"""Milvus 2.6 vs PostgreSQL/pgvector benchmark — Fase 1.6j.

Compares pgvector (baseline) against Milvus 2.6 as derived vector index
for the same 25 breaking-point cases.

PostgreSQL remains source of truth. Milvus is experimental only.

Usage:
  uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py --reset-collection
  uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py [--index-only] [--benchmark-only]
  uv run python lab/milvus-pgvector-benchmark/run_milvus_benchmark.py --dry-run

Environment:
  OPENAI_API_KEY or OpenAI_Key_JAI_query  (for query embeddings)
  DB_PG_V360_URL or TEAM360_DB_URL_PSQL  (PostgreSQL DSN)
  MILVUS_URI (optional, default: http://localhost:19530)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------
try:
    import pymilvus
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LAB_DIR = Path(__file__).parent
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
BP_FILE = LAB_DIR.parent / "postgres-knowledge-retrieval-breaking-points" / "golden_cases" / "breaking_point_cases.json"
RESULTS_DIR = LAB_DIR / "results"

sys.path.insert(0, str(BACKEND_DIR))

# Add the breaking-points lab directory for shared utilities
_BP_LAB = LAB_DIR.parent / "postgres-knowledge-retrieval-breaking-points"
sys.path.insert(0, str(_BP_LAB))

# ---------------------------------------------------------------------------
# Shared from reranking experiment
# ---------------------------------------------------------------------------
from run_reranking_experiment import (
    normalize, _content_text, _build_result_text,
    evaluate_strict, evaluate_normalized,
    passed_condition, _resolve_dsn, _validate_positive, load_cases,
    SCORE_NO_RESULT,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLLECTION_NAME = "team360_lab_pgvector_benchmark_openai_small_1536"
DEFAULT_EMBEDDING_DIMS = 1536

_NORM_WS = re.compile(r"\s+")
_RE_ACCENT = re.compile(r"[\u0300-\u036f]")


def normalize_light(text: str) -> str:
    t = text.lower()
    t = t.replace("_", " ").replace("-", " ")
    t = _NORM_WS.sub(" ", t).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    return _RE_ACCENT.sub("", nfkd)


# ---------------------------------------------------------------------------
# Embedding reader from PostgreSQL
# ---------------------------------------------------------------------------
async def load_embeddings_from_pg(
    conn: Any,
    knowledge_scope_id: str,
    embedding_version: str,
    limit: int = 500,
) -> list[dict]:
    sql = """
        select
            kce.chunk_embedding_id::text,
            kc.id::text as chunk_id,
            kc.knowledge_document_id::text as document_id,
            kc.title,
            kc.content as content_preview,
            kc.node_path,
            kce.embedding as embedding_vec,
            kce.knowledge_scope_id::text as scope_id,
            kce.metadata_jsonb->>'embedding_version' as emb_version
        from knowledge_chunk_embeddings kce
        join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
        where kce.embedding_status = 'ready'
          and kce.knowledge_scope_id = %(scope_id)s
          and kce.metadata_jsonb->>'embedding_version' = %(emb_version)s
          and kce.embedding is not null
        order by kc.chunk_index
        limit %(limit)s
    """
    rows = await conn.execute(sql, {
        "scope_id": knowledge_scope_id,
        "emb_version": embedding_version,
        "limit": limit,
    })
    return await rows.fetchall() or []


def _parse_embedding_vec(row: dict) -> list[float]:
    vec = row["embedding_vec"]
    if isinstance(vec, str):
        import ast
        return ast.literal_eval(vec)
    return list(vec)


# ---------------------------------------------------------------------------
# Milvus index operations
# ---------------------------------------------------------------------------
def create_milvus_collection(client: Any, collection_name: str, reset: bool = False) -> None:
    from pymilvus.milvus_client.index import IndexParams
    existing = client.list_collections()
    if collection_name in existing:
        if reset:
            client.drop_collection(collection_name)
            print(f"  Dropped existing collection: {collection_name}")
        else:
            print(f"  Collection already exists: {collection_name}")
            stats = client.get_collection_stats(collection_name)
            print(f"    Row count: {stats.get('row_count', '?')}")
            return

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=128)
    schema.add_field("document_id", DataType.VARCHAR, max_length=128)
    schema.add_field("knowledge_scope_id", DataType.VARCHAR, max_length=64)
    schema.add_field("embedding_version", DataType.VARCHAR, max_length=64)
    schema.add_field("content_preview", DataType.VARCHAR, max_length=2048)
    schema.add_field("node_path", DataType.VARCHAR, max_length=256)
    schema.add_field("title", DataType.VARCHAR, max_length=256)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=DEFAULT_EMBEDDING_DIMS)

    ip = IndexParams()
    ip.add_index(field_name="embedding", metric_type="COSINE", index_type="HNSW", params={"M": 16, "efConstruction": 200})

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=ip,
    )
    print(f"  Created collection: {collection_name}")
    client.flush(collection_name)


def index_embeddings_to_milvus(
    client: Any,
    collection_name: str,
    embeddings: list[dict],
) -> int:
    rows = []
    for i, emb in enumerate(embeddings):
        vec = _parse_embedding_vec(emb)
        row = {
            "id": i + 1,
            "chunk_id": emb["chunk_id"],
            "document_id": emb["document_id"],
            "knowledge_scope_id": emb["scope_id"],
            "embedding_version": emb.get("emb_version", ""),
            "content_preview": (emb["content_preview"] or "")[:2000],
            "node_path": emb.get("node_path") or "",
            "title": emb.get("title") or "",
            "embedding": vec,
        }
        rows.append(row)

    batch_size = 100
    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        result = client.insert(collection_name=collection_name, data=batch)
        total += result.get("insert_count", 0)

    client.flush(collection_name)
    return total


def create_milvus_index(client: Any, collection_name: str) -> None:
    from pymilvus.milvus_client.index import IndexParams
    ip = IndexParams()
    ip.add_index(field_name="embedding", metric_type="COSINE", index_type="HNSW", params={"M": 16, "efConstruction": 200})
    client.create_index(collection_name=collection_name, index_params=ip)
    print("  Index created (HNSW, COSINE)")
    client.flush(collection_name)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------
def search_milvus(
    client: Any,
    collection_name: str,
    query_embedding: list[float],
    top_k: int,
) -> list[dict]:
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


# ---------------------------------------------------------------------------
# Embed query via OpenAI (same for both pgvector and Milvus)
# ---------------------------------------------------------------------------
def embed_query(query: str, api_key: str, model: str = "text-embedding-3-small", dims: int = 1536) -> list[float]:
    import httpx
    resp = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"input": [query], "model": model, "dimensions": dims},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------
def classify_milvus_failure(
    case: dict,
    candidates: list[dict],
    reranked_results: list[dict],
) -> str:
    expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
    found_in_any = False
    for r in candidates:
        text = normalize(_content_text(r))
        if any(e in text for e in expected_norm):
            found_in_any = True
            break
    if not found_in_any:
        return "correct_not_in_candidates"
    if not reranked_results:
        return "retrieval_error"
    forbidden_norm = [normalize(c) for c in case.get("forbidden_concepts", [])]
    top5_text = _build_result_text(reranked_results, 5)
    for f in forbidden_norm:
        if f in top5_text:
            return "forbidden_concepts_still_present"
    return "ranking_still_insufficient"


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def generate_milvus_markdown(summary: dict, results: list[dict], args: argparse.Namespace) -> str:
    lines = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# Milvus 2.6 vs PostgreSQL/pgvector benchmark — Fase 1.6j")
    lines.append("")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Candidate pool (top-N):** {args.top_n}")
    lines.append(f"**Evaluation (top-K):** {args.top_k}")
    lines.append(f"**Collection:** {args.collection_name}")
    lines.append(f"**Indexed embeddings:** {summary.get('indexed_count', 0)}")
    lines.append(f"**Query embedding:** {args.embedding_model} ({DEFAULT_EMBEDDING_DIMS}d)")
    lines.append(f"**Scope:** {args.knowledge_scope_code}")
    lines.append("")

    pg = summary["pgvector_pass_rate"]
    mv = summary["milvus_pass_rate"]
    delta = round(mv - pg, 1)
    overlap_t5 = summary.get("candidate_overlap_top5", 0)
    overlap_t20 = summary.get("candidate_overlap_top20", 0)

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **pgvector pass rate:** {summary['pgvector_pass_norm']}/{summary['total_queries']} ({pg}%)")
    lines.append(f"- **Milvus pass rate:** {summary['milvus_pass_norm']}/{summary['total_queries']} ({mv}%)")
    lines.append(f"- **Delta (Milvus - pgvector):** {delta:+.1f}%")
    lines.append(f"- **Candidate overlap top-5:** {overlap_t5:.1f}%")
    lines.append(f"- **Candidate overlap top-20:** {overlap_t20:.1f}%")
    lines.append(f"- **Correct in pgvector top-N:** {summary['correct_in_pgvector']}/{summary['total_queries']}")
    lines.append(f"- **Correct in Milvus top-N:** {summary['correct_in_milvus']}/{summary['total_queries']}")
    lines.append(f"- **Cases improved by Milvus:** {summary['cases_improved']}")
    lines.append(f"- **Cases worsened by Milvus:** {summary['cases_worsened']}")
    lines.append(f"- **Cases same:** {summary['cases_same']}")
    lines.append(f"- **Forbidden concepts pgvector:** {summary['forbidden_pgvector']}")
    lines.append(f"- **Forbidden concepts Milvus:** {summary['forbidden_milvus']}")
    lines.append(f"- **Avg latency pgvector:** {summary['avg_latency_pgvector_ms']}ms")
    lines.append(f"- **Avg latency Milvus:** {summary['avg_latency_milvus_ms']}ms")
    lines.append(f"- **Indexing time:** {summary.get('indexing_time_s', 0):.1f}s")
    lines.append("")
    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Arquitectura evaluada")
    lines.append("")
    lines.append("PostgreSQL 18 como source of truth + pgvector como baseline.")
    lines.append("Milvus 2.6 como índice vectorial derivado experimental, poblado desde los")
    lines.append("mismos embeddings de PostgreSQL, sin llamar a OpenAI para corpus.")
    lines.append("PostgreSQL sigue siendo source of truth. Milvus no reemplaza PostgreSQL.")
    lines.append("")

    lines.append("## Calidad de retrieval")
    lines.append("")
    lines.append(f"| Métrica | pgvector | Milvus |")
    lines.append(f"|---------|----------|--------|")
    lines.append(f"| Pass rate | {pg}% | {mv}% |")
    lines.append(f"| Correct in top-N | {summary['correct_in_pgvector']}/{summary['total_queries']} | {summary['correct_in_milvus']}/{summary['total_queries']} |")
    lines.append(f"| Candidate overlap top-5 | — | {overlap_t5:.1f}% |")
    lines.append(f"| Candidate overlap top-20 | — | {overlap_t20:.1f}% |")
    lines.append("")

    lines.append("## Latencia")
    lines.append("")
    lines.append(f"- pgvector avg retrieval: {summary['avg_latency_pgvector_ms']}ms")
    lines.append(f"- Milvus avg retrieval:   {summary['avg_latency_milvus_ms']}ms")
    lines.append(f"- Diferencia:            {round(summary['avg_latency_pgvector_ms'] - summary['avg_latency_milvus_ms'], 1)}ms")
    lines.append("")

    lines.append("## Casos donde Milvus ayudó")
    lines.append("")
    helped = [r for r in results if r.get("milvus_helped")]
    if helped:
        for h in helped:
            lines.append(f"- `{h['case_id']}` — {h['query'][:60]}")
    else:
        lines.append("- Milvus no mejoró ningún caso respecto a pgvector.")
    lines.append("")

    lines.append("## Casos donde Milvus no ayudó")
    lines.append("")
    worsened = [r for r in results if r.get("baseline_norm", {}).get("passed", False) and not r.get("milvus_norm", {}).get("passed", False)]
    if worsened:
        for w in worsened:
            lines.append(f"- `{w['case_id']}` — {w['query'][:60]}")
    else:
        lines.append("- Milvus no empeoró ningún caso respecto a pgvector.")
    lines.append("")

    lines.append("## Casos donde ambos fallan por content_gap")
    lines.append("")
    both_fail = [r for r in results if not r.get("baseline_norm", {}).get("passed", False) and not r.get("milvus_norm", {}).get("passed", False)]
    content_gap = [r for r in both_fail if not r.get("correct_in_candidates_pg")]
    if content_gap:
        for cg in content_gap:
            lines.append(f"- `{cg['case_id']}` — {cg['query'][:60]}")
    else:
        lines.append("- No hay casos donde el candidato correcto falte en ambos sistemas.")
    lines.append("")

    fc = summary.get("failure_classification", {})
    if fc:
        lines.append("## Clasificación de fallos Milvus")
        lines.append("")
        for reason, count in sorted(fc.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_milvus"] * 100, 1) if summary["total_failed_milvus"] else 0
            lines.append(f"- **{reason}:** {count} ({pct}%)")
        lines.append("")

    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.6j — Milvus 2.6 vs PostgreSQL/pgvector Benchmark. "
                 "PostgreSQL source of truth, Milvus derived index. "
                 "No LLM, no ArangoDB, no production changes._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Blocked status
# ---------------------------------------------------------------------------
def print_blocked() -> None:
    print("=" * 70)
    print("MILVUS 2.6 BENCHMARK — Fase 1.6j")
    print("=" * 70)
    print()
    print("  STATUS: BLOCKED")
    print()
    if not PYMILVUS_AVAILABLE:
        print("  pymilvus is not installed.")
        print()
        print("  To install:")
        print("    cd SrvRestAstroLS_v1/backend")
        print("    uv add pymilvus")
    print("  No data was indexed. No results were generated.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Milvus 2.6 vs PostgreSQL/pgvector benchmark — Fase 1.6j")
    parser.add_argument("--top-n", type=_validate_positive, default=20, help="Candidate pool size (1-50)")
    parser.add_argument("--top-k", type=_validate_positive, default=5, help="Evaluation window (1-50)")
    parser.add_argument("--collection-name", default=COLLECTION_NAME)
    parser.add_argument("--reset-collection", action="store_true", help="Drop and recreate Milvus collection")
    parser.add_argument("--index-only", action="store_true", help="Only index embeddings, skip benchmark")
    parser.add_argument("--benchmark-only", action="store_true", help="Only run benchmark, skip indexing")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_EMBEDDING_DIMS)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.top_n < args.top_k:
        print(f"ERROR: --top-n ({args.top_n}) must be >= --top-k ({args.top_k})", file=sys.stderr)
        sys.exit(1)

    if not PYMILVUS_AVAILABLE:
        print_blocked()
        sys.exit(0)

    global MilvusClient, DataType
    from pymilvus import MilvusClient, DataType

    cases = load_cases(BP_FILE)
    print(f"Loaded {len(cases)} breaking point cases from {BP_FILE}")

    if args.max_cases:
        cases = cases[:args.max_cases]
        print(f"Limited to {len(cases)} cases")

    dsn = _resolve_dsn()
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    milvus_uri = os.environ.get("MILVUS_URI", "http://localhost:19530")

    print(f"PostgreSQL: {dsn[:20]}...")
    print(f"Milvus:     {milvus_uri}")
    print(f"Scope:      {args.knowledge_scope_code}")
    print(f"Top-N:      {args.top_n} | Top-K: {args.top_k}")
    print()

    if args.dry_run:
        print("DRY RUN — Validating Milvus connectivity and case loading (no indexing, no benchmark)")
        client = MilvusClient(uri=milvus_uri)
        existing = client.list_collections()
        print(f"  Milvus collections: {existing}")
        print(f"  Cases loaded: {len(cases)}")
        print("  Dry run OK.")
        sys.exit(0)

    import asyncio
    import psycopg
    from psycopg.rows import dict_row
    from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository

    repo = KnowledgeIngestionRepository()

    async def run_all():
        conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
        await conn.set_autocommit(True)

        try:
            # Resolve scope ID
            ctx = await repo.resolve_ingestion_context(
                conn=conn,
                organization_code=args.organization_code,
                workspace_code=args.workspace_code,
                knowledge_scope_code=args.knowledge_scope_code,
            )
            scope_id = ctx.knowledge_scope_id
            print(f"Knowledge scope ID: {scope_id}")
            print()

            # Indexing phase
            indexed_count = 0
            client = MilvusClient(uri=milvus_uri)

            if not args.benchmark_only:
                print("=" * 70)
                print("INDEXING PHASE")
                print("=" * 70)
                print()

                t_index_start = time.time()

                print("Loading embeddings from PostgreSQL...")
                embeddings = await load_embeddings_from_pg(
                    conn=conn,
                    knowledge_scope_id=scope_id,
                    embedding_version=args.embedding_version,
                )
                print(f"  Found {len(embeddings)} embeddings ready")
                print()

                if len(embeddings) == 0:
                    print("ERROR: No embeddings found in PostgreSQL", file=sys.stderr)
                    return None, None, None

                print("Creating/resetting Milvus collection...")
                create_milvus_collection(client, args.collection_name, reset=args.reset_collection)
                print()

                print("Indexing embeddings to Milvus...")
                indexed_count = index_embeddings_to_milvus(client, args.collection_name, embeddings)
                print(f"  Inserted: {indexed_count}")
                print()

                print("Creating HNSW index on Milvus collection...")
                create_milvus_index(client, args.collection_name)
                print()

                indexing_time_s = round(time.time() - t_index_start, 1)
                print(f"Indexing completed in {indexing_time_s}s")
                print()
            else:
                stats = client.get_collection_stats(args.collection_name)
                indexed_count = stats.get("row_count", 0)
                print(f"Skipping indexing. Collection has {indexed_count} rows.")
                indexing_time_s = 0.0

            # Benchmark phase
            if args.index_only:
                print("--index-only: Benchmark skipped.")
                return None, None, None

            print("=" * 70)
            print("BENCHMARK PHASE")
            print("=" * 70)
            print()

            from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
            worker = KnowledgeIngestionWorker()

            case_results = []
            pg_latencies: list[float] = []
            mv_latencies: list[float] = []

            for case in cases:
                case_id = case["case_id"]
                query = case["query"]
                print(f"  [{case_id}] Querying both systems...", end=" ", flush=True)

                # Embed query once (shared)
                t_emb = time.time()
                query_emb = embed_query(query, api_key, model=args.embedding_model, dims=args.dimensions)
                embed_latency = (time.time() - t_emb) * 1000

                # --- pgvector ---
                t0 = time.time()
                try:
                    pg_result = await worker.retrieve_knowledge_chunks(
                        conn=conn,
                        organization_code=args.organization_code,
                        workspace_code=args.workspace_code,
                        knowledge_scope_code=args.knowledge_scope_code,
                        query=query,
                        embedding_model=args.embedding_model,
                        embedding_dimensions=args.dimensions,
                        embedding_version=args.embedding_version,
                        limit=args.top_n,
                    )
                except Exception as e:
                    print(f"PG ERROR: {str(e)[:60]}", flush=True)
                    pg_latencies.append(0)
                    mv_latencies.append(0)
                    case_results.append({
                        "case_id": case_id, "query": query,
                        "category": case.get("category", ""),
                        "risk_level": case.get("risk_level", "unknown"),
                        "expected_concepts": case.get("expected_concepts", []),
                        "pg_candidate_count": 0, "mv_candidate_count": 0,
                        "retrieval_error": str(e)[:200],
                        "baseline_norm": {"passed": False, "score": SCORE_NO_RESULT},
                        "milvus_norm": {"passed": False, "score": SCORE_NO_RESULT},
                        "milvus_helped": False,
                        "correct_in_candidates_pg": False,
                        "correct_in_candidates_mv": False,
                        "failure_classification": "retrieval_error",
                    })
                    continue

                pg_lat = (time.time() - t0) * 1000
                pg_latencies.append(pg_lat)
                pg_candidates = pg_result.get("results", [])

                # --- Milvus ---
                t1 = time.time()
                mv_candidates = search_milvus(client, args.collection_name, query_emb, args.top_n)
                mv_lat = (time.time() - t1) * 1000
                mv_latencies.append(mv_lat)

                pg_top_k = pg_candidates[:args.top_k] if len(pg_candidates) >= args.top_k else pg_candidates
                mv_top_k = mv_candidates[:args.top_k] if len(mv_candidates) >= args.top_k else mv_candidates

                eval_pg = evaluate_normalized(case, pg_top_k, args.top_n)
                eval_mv = evaluate_normalized(case, mv_top_k, args.top_n)

                # Check if correct candidate is in pools
                expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
                pg_correct = any(
                    any(e in normalize(_content_text(c)) for e in expected_norm)
                    for c in pg_candidates
                )
                mv_correct = any(
                    any(e in normalize(_content_text(c)) for e in expected_norm)
                    for c in mv_candidates
                )

                milvus_helped = (not eval_pg["passed"]) and eval_mv["passed"]

                failure_classification = ""
                if not eval_mv["passed"]:
                    failure_classification = classify_milvus_failure(case, mv_candidates, mv_top_k)

                case_results.append({
                    "case_id": case_id, "query": query,
                    "category": case.get("category", ""),
                    "risk_level": case.get("risk_level", ""),
                    "pass_criteria": case.get("pass_criteria", "top5_contains_expected"),
                    "expected_concepts": case.get("expected_concepts", []),
                    "pg_candidate_count": len(pg_candidates),
                    "mv_candidate_count": len(mv_candidates),
                    "correct_in_candidates_pg": pg_correct,
                    "correct_in_candidates_mv": mv_correct,
                    "pg_latency_ms": round(pg_lat, 1),
                    "mv_latency_ms": round(mv_lat, 1),
                    "baseline_norm": eval_pg,
                    "milvus_norm": eval_mv,
                    "milvus_helped": milvus_helped,
                    "failure_classification": failure_classification,
                })

                pg_pass = "P" if eval_pg["passed"] else "F"
                mv_pass = "P" if eval_mv["passed"] else "F"
                flag = " 🎯 MV" if milvus_helped else ""
                print(f"pg={pg_pass} mv={mv_pass} | pg_correct={pg_correct} mv_correct={mv_correct} | {pg_lat:.0f}ms / {mv_lat:.0f}ms{flag}", flush=True)

            return case_results, pg_latencies, mv_latencies, client

        finally:
            await conn.close()

    result = asyncio.run(run_all())
    if result is None or result[0] is None:
        print("Benchmark aborted or index-only mode.")
        sys.exit(0)

    case_results, pg_latencies, mv_latencies, client = result

    # Compute summary
    total = len(case_results)
    pg_passed = sum(1 for r in case_results if r.get("baseline_norm", {}).get("passed", False))
    mv_passed = sum(1 for r in case_results if r.get("milvus_norm", {}).get("passed", False))

    high_risk_total = sum(1 for r in case_results if r.get("risk_level") == "high")
    high_risk_pg = sum(1 for r in case_results if r.get("risk_level") == "high" and r.get("baseline_norm", {}).get("passed", False))
    high_risk_mv = sum(1 for r in case_results if r.get("risk_level") == "high" and r.get("milvus_norm", {}).get("passed", False))

    improved = sum(1 for r in case_results if r.get("milvus_helped"))
    worsened = sum(1 for r in case_results if r.get("baseline_norm", {}).get("passed", False) and not r.get("milvus_norm", {}).get("passed", False))
    same = total - improved - worsened

    pg_correct_count = sum(1 for r in case_results if r.get("correct_in_candidates_pg"))
    mv_correct_count = sum(1 for r in case_results if r.get("correct_in_candidates_mv"))

    forbidden_pg = sum(len(r.get("baseline_norm", {}).get("forbidden_in_top3", [])) for r in case_results)
    forbidden_mv = sum(len(r.get("milvus_norm", {}).get("forbidden_in_top3", [])) for r in case_results)

    avg_pg_lat = round(sum(pg_latencies) / len(pg_latencies), 1) if pg_latencies else 0
    avg_mv_lat = round(sum(mv_latencies) / len(mv_latencies), 1) if mv_latencies else 0

    pg_rate = round(pg_passed / total * 100, 1) if total else 0
    mv_rate = round(mv_passed / total * 100, 1) if total else 0

    # Candidate overlap
    overlap_scores_t5 = []
    overlap_scores_t20 = []
    for r in case_results:
        pass

    failure_classification: dict[str, int] = {}
    for r in case_results:
        fc = r.get("failure_classification", "")
        if fc:
            failure_classification[fc] = failure_classification.get(fc, 0) + 1

    # Decision rules
    if mv_rate > pg_rate + 5 and mv_rate >= 55:
        rec = "B. Evaluar Milvus como índice derivado por recall — mejora pass rate."
    elif mv_rate > pg_rate:
        rec = "C. Evaluar Milvus como índice derivado por recall — mejora marginal."
    elif avg_mv_lat < avg_pg_lat * 0.7:
        rec = "D. Evaluar Milvus como índice derivado por latencia — significativamente más rápido."
    elif mv_rate < pg_rate:
        rec = "A. Mantener pgvector como runtime inicial — Milvus no mejora calidad."
    else:
        rec = "A. Mantener pgvector como runtime inicial — Milvus no justifica complejidad."

    if mv_correct_count < 15 and pg_correct_count < 15:
        rec += " Ambos fallan por content_gap, no por backend vectorial."
    elif mv_rate >= 60 and mv_rate >= pg_rate:
        rec += " Milvus puede ser complemento operativo en etapa de escala."

    stats = client.get_collection_stats(args.collection_name)
    collection_size = stats.get("row_count", 0)

    summary = {
        "experiment": "Milvus 2.6 vs PostgreSQL/pgvector benchmark — Fase 1.6j",
        "collection_name": args.collection_name,
        "embedding_model": args.embedding_model,
        "embedding_version": args.embedding_version,
        "dimensions": args.dimensions,
        "knowledge_scope": args.knowledge_scope_code,
        "top_n": args.top_n,
        "top_k": args.top_k,
        "total_queries": total,
        "indexed_count": collection_size,
        "indexing_time_s": 0.0,
        "pgvector_pass_norm": pg_passed,
        "pgvector_pass_rate": pg_rate,
        "milvus_pass_norm": mv_passed,
        "milvus_pass_rate": mv_rate,
        "delta_pass_rate": round(mv_rate - pg_rate, 1),
        "high_risk_total": high_risk_total,
        "high_risk_pgvector": high_risk_pg,
        "high_risk_milvus": high_risk_mv,
        "cases_improved": improved,
        "cases_worsened": worsened,
        "cases_same": same,
        "correct_in_pgvector": pg_correct_count,
        "correct_in_milvus": mv_correct_count,
        "forbidden_pgvector": forbidden_pg,
        "forbidden_milvus": forbidden_mv,
        "avg_latency_pgvector_ms": avg_pg_lat,
        "avg_latency_milvus_ms": avg_mv_lat,
        "total_failed_milvus": total - mv_passed,
        "failure_classification": dict(sorted(failure_classification.items(), key=lambda x: -x[1])),
        "architecture_recommendation": rec,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"milvus_pgvector_benchmark_{ts}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": case_results,
        "latencies_ms": {"pgvector": pg_latencies, "milvus": mv_latencies},
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_milvus_markdown(summary, case_results, args))
    print(f"Report saved: {md_path}")

    print()
    print("=" * 70)
    print("MILVUS BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"  Total cases:          {total}")
    print(f"  pgvector pass:        {pg_passed}/{total} ({pg_rate}%)")
    print(f"  Milvus pass:          {mv_passed}/{total} ({mv_rate}%)")
    print(f"  Delta:                {summary['delta_pass_rate']:+.1f}%")
    print(f"  High-risk pg/mv:      {high_risk_pg}/{high_risk_mv} (of {high_risk_total})")
    print(f"  Improved/worsened:    {improved}/{worsened}")
    print(f"  Correct pg/mv:        {pg_correct_count}/{mv_correct_count}")
    print(f"  Forbidden pg/mv:      {forbidden_pg}/{forbidden_mv}")
    print(f"  Avg lat pg/mv:        {avg_pg_lat}ms / {avg_mv_lat}ms")
    print(f"  Recommendation: {rec}")


if __name__ == "__main__":
    main()
