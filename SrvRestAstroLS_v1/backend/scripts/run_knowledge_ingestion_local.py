"""Local integration test for Knowledge Ingestion Fase 1.4a.

Runs persist_package_documents against the real PostgreSQL DB.
No endpoints, no frontend, no embeddings, no Milvus, no ArangoDB.

Usage (from backend/):

    DB_PG_V360_URL="postgresql://..." uv run python scripts/run_knowledge_ingestion_local.py
    DB_PG_V360_URL="postgresql://..." uv run python scripts/run_knowledge_ingestion_local.py --dry-run

Requires migrations 006 and 007 applied.
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
    parser = argparse.ArgumentParser(description="Local knowledge ingestion integration")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Run in dry-run mode (default: True)")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run",
                        help="Run real persistence")
    parser.add_argument("--include-chunks", action="store_true", default=True,
                        help="Generate chunks (default: True)")
    parser.add_argument("--no-chunks", action="store_false", dest="include_chunks",
                        help="Skip chunk generation")
    args = parser.parse_args()

    dsn = _resolve_dsn()
    print(f"Connecting to DB: {dsn[:20]}...")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print("ERROR: psycopg not installed", file=sys.stderr)
        sys.exit(1)

    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    package_root = str(
        project_root / "knowledge" / "packages" / "pkg_sales_diagnosis"
    )
    if not Path(package_root).is_dir():
        print(f"ERROR: package_root not found: {package_root}", file=sys.stderr)
        sys.exit(1)

    import asyncio

    async def run() -> None:
        conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
        await conn.set_autocommit(True)
        try:
            worker = KnowledgeIngestionWorker()
            result = await worker.persist_package_documents(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                package_root=package_root,
                assistant_instance_code="team360_sales_diagnosis",
                triggered_by_email="mario.rojas.marconi@gmail.com",
                dry_run=args.dry_run,
                include_chunks=args.include_chunks,
            )
        finally:
            await conn.close()

        print()
        print("=" * 55)
        print("KNOWLEDGE INGESTION RESULT")
        print("=" * 55)
        print(f"  Mode:              {'DRY RUN' if args.dry_run else 'PERSIST'}")
        print(f"  Package:           {result.package_code}")
        print(f"  Package root:      {result.package_root}")
        print(f"  Scanned:           {result.scanned_count}")
        print(f"  Candidates:        {result.candidate_count}")
        print(f"  Inserted docs:     {result.inserted_count}")
        print(f"  Updated docs:      {result.updated_count}")
        print(f"  Unchanged docs:    {result.unchanged_count}")
        print(f"  Skipped docs:      {result.skipped_count}")
        print(f"  Invalid docs:      {result.invalid_count}")
        print(f"  Total chunks:      {result.total_chunk_count}")
        print(f"  Run ID:            {result.run_id or '(none)'}")
        print()

        if result.errors:
            print("  ERRORS:")
            for e in result.errors:
                print(f"    - {e}")
        if result.warnings:
            print("  WARNINGS:")
            for w in result.warnings:
                print(f"    - {w}")

        print()
        for d in result.documents:
            status_icon = {
                "inserted": "✓", "updated": "~", "unchanged": "=",
                "skipped": "-", "invalid": "✗",
            }.get(d.status, "?")
            print(
                f"  [{status_icon}] {d.relative_path} "
                f"→ {d.status}"
                f"{f' ({d.chunk_count} chunks)' if d.chunk_count else ''}"
            )
            for e in d.errors:
                print(f"         error: {e}")
            for w in d.warnings:
                print(f"         warn:  {w}")

        print()
        if not args.dry_run and result.run_id:
            print("  Run completed. DB now has data in:")
            print("    - knowledge_ingestion_runs")
            print("    - knowledge_documents")
            print("    - knowledge_chunks")
        elif args.dry_run:
            print("  Dry-run: no data written.")

    asyncio.run(run())


if __name__ == "__main__":
    main()
