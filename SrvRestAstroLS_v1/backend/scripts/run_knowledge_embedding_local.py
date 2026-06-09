"""Local integration script for Knowledge Ingestion Fase 1.5 — Embeddings.

Generates OpenAI text-embedding-3-small embeddings for pending chunks.
No endpoints, no frontend, no Milvus, no ArangoDB, no retrieval.

Usage (from backend/):

    OPENAI_API_KEY="sk-..." DB_PG_V360_URL="postgresql://..." uv run python scripts/run_knowledge_embedding_local.py

    uv run python scripts/run_knowledge_embedding_local.py --dry-run
    uv run python scripts/run_knowledge_embedding_local.py --no-dry-run --limit 20

Requires migrations 003 and 006 applied.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.db.transaction import transaction
from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker


def _resolve_dsn() -> str:
    src = os.environ.get("DB_PG_V360_URL") or os.environ.get("TEAM360_DB_URL_PSQL")
    if not src:
        print("ERROR: Set DB_PG_V360_URL or TEAM360_DB_URL_PSQL", file=sys.stderr)
        sys.exit(1)
    parts = urlsplit(src)
    scheme = "postgresql" if parts.scheme.startswith("postgresql") else parts.scheme
    return urlunsplit((scheme, parts.netloc, "/team360", parts.query, parts.fragment))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local knowledge embedding generation")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Run in dry-run mode (default: True)")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run",
                        help="Run real embedding generation")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--package-code", default=None)
    parser.add_argument("--assistant-instance-code", default=None)
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    dsn = _resolve_dsn()
    print(f"Connecting to DB: {dsn[:20]}...")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print("ERROR: psycopg not installed", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment", file=sys.stderr)
        sys.exit(1)
    key_preview = api_key[:8] + "..." if len(api_key) > 8 else "(invalid)"
    print(f"OpenAI API key: {key_preview}")

    import asyncio

    async def run() -> None:
        conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
        await conn.set_autocommit(True)
        try:
            worker = KnowledgeIngestionWorker()
            result = await worker.embed_pending_chunks(
                conn=conn,
                organization_code=args.organization_code,
                workspace_code=args.workspace_code,
                knowledge_scope_code=args.knowledge_scope_code,
                package_code=args.package_code,
                assistant_instance_code=args.assistant_instance_code,
                embedding_model=args.embedding_model,
                embedding_dimensions=args.dimensions,
                embedding_version=args.embedding_version,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        finally:
            await conn.close()

        print()
        print("=" * 55)
        print("KNOWLEDGE EMBEDDING RESULT")
        print("=" * 55)
        print(f"  Mode:              {'DRY RUN' if result['dry_run'] else 'EMBED'}")
        print(f"  Knowledge scope:   {result.get('knowledge_scope_id', '(none)')}")
        print(f"  Embedding model:   {result.get('embedding_model', '-')}")
        print(f"  Dimensions:        {result.get('embedding_dimensions', '-')}")
        print(f"  Embedding version: {result.get('embedding_version', '-')}")
        print(f"  Pending chunks:    {result.get('pending_count', 0)}")
        print(f"  Embedded:          {result.get('embedded_count', 0)}")
        print(f"  Skipped:           {result.get('skipped_count', 0)}")
        print(f"  Errors:            {result.get('error_count', 0)}")
        print()

        if result.get("dry_run") and result.get("chunks"):
            print("  Pending chunks preview:")
            for c in result["chunks"]:
                print(f"    [{c['chunk_index']}] {c['title']} "
                      f"({c['content_length']} chars)")

        errors = result.get("errors", [])
        if errors:
            print("  ERRORS:")
            for e in errors:
                print(f"    - {e}")

        if result["dry_run"]:
            print("  Dry-run: no embeddings generated, no DB writes.")
        else:
            print(f"  Embeddings written: {result['embedded_count']} inserted, "
                  f"{result.get('skipped_count', 0)} skipped, "
                  f"{result.get('error_count', 0)} errors")

    asyncio.run(run())


if __name__ == "__main__":
    main()
