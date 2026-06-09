"""Local integration script for Knowledge Ingestion Fase 1.6a — Retrieval.

Generates an OpenAI embedding for the query, then searches pgvector for the
most similar knowledge chunks within the given knowledge scope.

No endpoints, no frontend, no Milvus, no ArangoDB, no LLM chat completion.

Usage (from backend/):

    OPENAI_API_KEY="sk-..." DB_PG_V360_URL="postgresql://..." uv run python scripts/run_knowledge_retrieval_local.py \\
        --query "¿Qué significa que algo sea automatizable pero no vendible hoy?"

    uv run python scripts/run_knowledge_retrieval_local.py --query "..." --limit 3

Requires migrations 003 applied and embeddings already generated (Fase 1.5).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker


def _resolve_dsn() -> str:
    src = os.environ.get("DB_PG_V360_URL") or os.environ.get("TEAM360_DB_URL_PSQL")
    if not src:
        print("ERROR: Set DB_PG_V360_URL or TEAM360_DB_URL_PSQL", file=sys.stderr)
        sys.exit(1)
    parts = urlsplit(src)
    scheme = "postgresql" if parts.scheme.startswith("postgresql") else parts.scheme
    return urlunsplit((scheme, parts.netloc, "/team360", parts.query, parts.fragment))


def _validate_limit(val: str) -> int:
    n = int(val)
    if n < 1 or n > 50:
        raise argparse.ArgumentTypeError(f"limit must be 1–50, got {n}")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Local knowledge retrieval via pgvector")
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--limit", type=_validate_limit, default=5,
                        help="Max results (1–50, default: 5)")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--min-score", type=float, default=None,
                        help="Minimum similarity score (0–1, optional)")
    args = parser.parse_args()

    dsn = _resolve_dsn()
    print(f"Connecting to DB: {dsn[:20]}...")

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment", file=sys.stderr)
        sys.exit(1)
    key_preview = api_key[:8] + "..." if len(api_key) > 8 else "(invalid)"
    print(f"OpenAI API key: {key_preview}")

    print()
    print("=" * 55)
    print("ATTENTION")
    print("=" * 55)
    print("  This script uses OpenAI (text-embedding-3-small) to embed the")
    print("  query text. Each call consumes API credits.")
    print("  Retrieval uses PostgreSQL/pgvector — NOT Milvus, NOT ArangoDB.")
    print("  No LLM chat completion is called.")
    print()

    import asyncio
    import psycopg
    from psycopg.rows import dict_row

    async def run() -> None:
        conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
        await conn.set_autocommit(True)
        try:
            worker = KnowledgeIngestionWorker()
            result = await worker.retrieve_knowledge_chunks(
                conn=conn,
                organization_code=args.organization_code,
                workspace_code=args.workspace_code,
                knowledge_scope_code=args.knowledge_scope_code,
                query=args.query,
                embedding_model=args.embedding_model,
                embedding_dimensions=args.dimensions,
                embedding_version=args.embedding_version,
                limit=args.limit,
                min_score=args.min_score,
            )
        finally:
            await conn.close()

        print()
        print("=" * 55)
        print("KNOWLEDGE RETRIEVAL RESULT")
        print("=" * 55)
        print(f"  Query:               {result['query']}")
        print(f"  Embedding model:     {result['embedding_model']}")
        print(f"  Dimensions:          {result['embedding_dimensions']}")
        print(f"  Embedding version:   {result['embedding_version']}")
        print(f"  Knowledge scope:     {result.get('knowledge_scope_id', '(none)')}")
        print(f"  Results:             {result['result_count']}")
        print()

        for r in result["results"]:
            print(f"  --- Rank {r['rank']} (score: {r['score']}) ---")
            print(f"  Chunk:     {r['chunk_id'][:8]}... (index {r['chunk_index']})")
            print(f"  Document:  {r['document_id'][:8]}...")
            print(f"  Source:    {r['source_uri']}")
            print(f"  Title:     {r['title']}")
            if r.get("node_path"):
                print(f"  Node path: {r['node_path']}")
            print(f"  --- Content preview (first 300 chars) ---")
            print(f"  {r['content_preview']}")
            print()

    asyncio.run(run())


if __name__ == "__main__":
    main()
