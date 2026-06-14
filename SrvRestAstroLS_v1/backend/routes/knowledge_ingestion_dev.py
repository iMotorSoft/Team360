"""Internal/dev API endpoint for Knowledge Ingestion Platform Service.

This is NOT a public endpoint. No upload, no Milvus, no real embeddings.
Designed for developer use to invoke the ingestion pipeline in a
controlled way:

    scan -> readiness gate -> markdown chunking -> persist/report

Modes:
  - dry_run (default): scan + gate + estimate chunks, no DB writes.
  - persist:          full pipeline with DB persistence via
                      KnowledgeIngestionWorker. Requires a configured
                      database (TEAM360_DB_URL or equivalent).
"""

from __future__ import annotations

from pathlib import Path

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_200_OK
from pydantic import BaseModel, Field

from modules.db.errors import DatabaseConfigurationError
from modules.db.pool import close_pool, create_pool, open_pool, set_pool
from modules.db.settings import DatabaseSettings, get_database_settings
from modules.knowledge_ingestion.markdown_chunker import chunk_markdown
from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
from modules.knowledge_ingestion.schemas import (
    PackageScanRequest,
    check_document_ingestion_readiness,
)
from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker


# ── Request / Response schemas ──────────────────────────────────────────────


class DevIngestDocumentResult(BaseModel):
    relative_path: str
    node_path: str | None = None
    status: str = ""
    ingestion_status: str = ""
    candidate_for_ingestion: bool = False
    gate_ready: bool = False
    chunk_count: int = 0
    error_codes: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    persisted: bool = False
    document_id: str | None = None


class DevIngestResponse(BaseModel):
    ok: bool = True
    mode: str = "dry_run"
    package_code: str = ""
    document_count: int = 0
    candidate_count: int = 0
    ready_count: int = 0
    rejected_count: int = 0
    chunk_count: int = 0
    documents: list[DevIngestDocumentResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    run_id: str | None = None
    persisted_document_count: int = 0
    persisted_chunk_count: int = 0


class DevIngestRequest(BaseModel):
    package_code: str
    package_path: str
    mode: str = "dry_run"
    include_drafts: bool = False
    chunking_strategy: str = "markdown"


# ── Path validation ─────────────────────────────────────────────────────────


def _validate_ingest_path(package_path: str) -> Path:
    raw = Path(package_path).as_posix()
    if ".." in raw.split("/"):
        raise HTTPException(
            status_code=422,
            detail="package_path must not contain path traversal (..)",
        )

    resolved = Path(package_path).resolve()

    if not resolved.exists():
        raise HTTPException(
            status_code=422,
            detail=f"package_path does not exist: {package_path}",
        )
    if not resolved.is_dir():
        raise HTTPException(
            status_code=422,
            detail=f"package_path is not a directory: {package_path}",
        )

    return resolved


# ── Database detection ──────────────────────────────────────────────────────


def _is_db_configured() -> bool:
    """Check whether a database URL is configured.

    Does NOT open a connection — only checks if settings can be
    resolved from environment variables.
    """
    try:
        get_database_settings()
        return True
    except DatabaseConfigurationError:
        return False


async def _run_persist_pipeline(
    package_code: str,
    package_root: str,
    include_drafts: bool,
    organization_code: str,
    workspace_code: str,
    knowledge_scope_code: str,
    assistant_instance_code: str | None = None,
) -> dict:
    """Execute the full persist pipeline against a real database.

    Can be monkeypatched in tests to avoid real DB dependency.
    Returns a dict with keys matching the response contract.
    """
    settings: DatabaseSettings = get_database_settings()
    pool = create_pool(settings)
    set_pool(pool)
    await open_pool(pool)

    try:
        async with pool.connection() as conn:
            worker = KnowledgeIngestionWorker()
            result = await worker.persist_package_documents(
                conn=conn,
                organization_code=organization_code,
                workspace_code=workspace_code,
                knowledge_scope_code=knowledge_scope_code,
                package_code=package_code,
                package_root=package_root,
                assistant_instance_code=assistant_instance_code,
                dry_run=False,
                include_chunks=True,
                chunk_strategy="structural",
            )
            return {
                "run_id": result.run_id,
                "persisted_document_count": result.persisted_count,
                "persisted_chunk_count": result.total_chunk_count,
                "inserted_count": result.inserted_count,
                "updated_count": result.updated_count,
                "unchanged_count": result.unchanged_count,
                "invalid_count": result.invalid_count,
                "skipped_count": result.skipped_count,
                "total_chunk_count": result.total_chunk_count,
                "persist_errors": result.errors,
                "persist_documents": [
                    {
                        "relative_path": d.relative_path,
                        "action": d.action,
                        "document_id": d.document_id,
                        "chunk_count": d.chunk_count,
                        "persist_status": d.status,
                        "persist_errors": d.errors,
                    }
                    for d in result.documents
                ],
            }
    finally:
        try:
            await close_pool(pool)
        except Exception:
            pass


# ── Handler ─────────────────────────────────────────────────────────────────


@post("/api/dev/knowledge-ingestion/ingest", status_code=HTTP_200_OK)
async def ingest_dev(data: DevIngestRequest) -> DevIngestResponse:
    package_code = data.package_code.strip() if data.package_code else ""
    if not package_code:
        raise HTTPException(status_code=422, detail="package_code is required")

    package_path_str = data.package_path.strip() if data.package_path else ""
    if not package_path_str:
        raise HTTPException(status_code=422, detail="package_path is required")

    package_root = _validate_ingest_path(package_path_str)

    mode = data.mode.strip().lower() if data.mode else "dry_run"
    if mode not in ("dry_run", "persist"):
        raise HTTPException(
            status_code=422,
            detail=f"mode must be 'dry_run' or 'persist', got {data.mode!r}",
        )

    chunking_strategy = data.chunking_strategy.strip() if data.chunking_strategy else "markdown"
    if chunking_strategy not in ("markdown",):
        raise HTTPException(
            status_code=422,
            detail=f"chunking_strategy must be 'markdown', got {data.chunking_strategy!r}",
        )

    # ── Scan package (shared between modes) ──────────────────────────────

    scanner = KnowledgePackageScanner()
    scan_request = PackageScanRequest(
        package_code=package_code,
        package_root=str(package_root),
        dry_run=True,
        include_drafts=data.include_drafts,
    )
    scan_result = scanner.scan(scan_request)

    # ── Per-document readiness gate ──────────────────────────────────────

    doc_results: list[DevIngestDocumentResult] = []
    total_chunks = 0
    ready_count = 0
    rejected_count = 0

    # Auto-detect org/workspace/scope codes from first ready document
    detected_org: str | None = None
    detected_ws: str | None = None
    detected_ks: str | None = None

    for doc in scan_result.documents:
        fm = doc.frontmatter or {}
        ingest_status = fm.get("ingestion_status", "")
        doc_status = fm.get("status", "")
        node_path = fm.get("node_path")

        gate = check_document_ingestion_readiness(fm, doc.relative_path)

        chunk_count = 0
        if gate.ready and doc.candidate_for_ingestion:
            if mode == "dry_run":
                try:
                    raw = doc.path.read_bytes()
                    chunks = chunk_markdown(raw.decode("utf-8"))
                    chunk_count = len(chunks)
                    total_chunks += chunk_count
                except Exception:
                    pass
            else:
                pass  # chunks counted from persist result

        if gate.ready:
            ready_count += 1
            if detected_org is None:
                detected_org = fm.get("organization_code")
                detected_ws = fm.get("workspace_code")
                detected_ks = fm.get("knowledge_scope_code")
        else:
            rejected_count += 1

        doc_results.append(DevIngestDocumentResult(
            relative_path=doc.relative_path,
            node_path=node_path,
            status=doc_status,
            ingestion_status=ingest_status,
            candidate_for_ingestion=doc.candidate_for_ingestion,
            gate_ready=gate.ready,
            chunk_count=chunk_count,
            error_codes=gate.error_codes,
            error_messages=gate.error_messages,
        ))

    # ── Persist mode ─────────────────────────────────────────────────────

    if mode == "persist":
        if not _is_db_configured():
            return DevIngestResponse(
                ok=False,
                mode="persist",
                package_code=package_code,
                errors=["persist mode requires a database connection: set TEAM360_DB_URL or equivalent"],
            )

        if not detected_org or not detected_ws or not detected_ks:
            return DevIngestResponse(
                ok=False,
                mode="persist",
                package_code=package_code,
                errors=[
                    "persist mode requires at least one ready document "
                    "with organization_code, workspace_code, and knowledge_scope_code"
                ],
            )

        try:
            persist_data = await _run_persist_pipeline(
                package_code=package_code,
                package_root=str(package_root),
                include_drafts=data.include_drafts,
                organization_code=detected_org,
                workspace_code=detected_ws,
                knowledge_scope_code=detected_ks,
            )
        except Exception as exc:
            return DevIngestResponse(
                ok=False,
                mode="persist",
                package_code=package_code,
                errors=[f"Persist pipeline failed: {exc}"],
            )

        # Merge persist results into doc_results, preserving scanner metadata
        persist_by_path: dict[str, dict] = {}
        for pd in persist_data["persist_documents"]:
            persist_by_path[pd["relative_path"]] = pd

        for dr in doc_results:
            p = persist_by_path.get(dr.relative_path)
            if p is not None:
                dr.persisted = p["action"] in ("inserted", "updated")
                dr.document_id = p["document_id"]
                if p["action"] == "unchanged":
                    dr.persisted = True  # already in DB, counts as persisted
                dr.chunk_count = p["chunk_count"]
                if p["persist_errors"]:
                    dr.error_messages.extend(p["persist_errors"])

        total_chunks = persist_data["total_chunk_count"]

        return DevIngestResponse(
            ok=not persist_data["persist_errors"],
            mode="persist",
            package_code=package_code,
            document_count=len(doc_results),
            candidate_count=scan_result.candidate_count,
            ready_count=ready_count,
            rejected_count=rejected_count,
            chunk_count=total_chunks,
            documents=doc_results,
            errors=persist_data["persist_errors"],
            run_id=persist_data["run_id"],
            persisted_document_count=persist_data["persisted_document_count"],
            persisted_chunk_count=persist_data["persisted_chunk_count"],
        )

    # ── Dry-run mode ─────────────────────────────────────────────────────

    return DevIngestResponse(
        ok=not scan_result.errors,
        mode=mode,
        package_code=package_code,
        document_count=len(doc_results),
        candidate_count=scan_result.candidate_count,
        ready_count=ready_count,
        rejected_count=rejected_count,
        chunk_count=total_chunks,
        documents=doc_results,
        errors=scan_result.errors,
    )
