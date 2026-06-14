"""Internal/dev API endpoint for Knowledge Ingestion Platform Service.

This is NOT a public endpoint. No upload, no Milvus, no real embeddings.
Designed for developer use to invoke the ingestion pipeline in a
controlled way:

    scan -> readiness gate -> markdown chunking -> persist/report

Modes:
  - dry_run (default): scan + gate + estimate chunks, no DB writes.
  - persist:          full pipeline; requires a database connection.
                      Returns error if no DB is available.
"""

from __future__ import annotations

import json
from pathlib import Path

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_200_OK
from pydantic import BaseModel, Field

from modules.knowledge_ingestion.markdown_chunker import chunk_markdown
from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.schemas import (
    PackageScanRequest,
    check_document_ingestion_readiness,
)


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

    if mode == "persist":
        return DevIngestResponse(
            ok=False,
            mode="persist",
            package_code=package_code,
            errors=["persist mode requires a database connection and is not yet available in this dev endpoint"],
        )

    chunking_strategy = data.chunking_strategy.strip() if data.chunking_strategy else "markdown"
    if chunking_strategy not in ("markdown",):
        raise HTTPException(
            status_code=422,
            detail=f"chunking_strategy must be 'markdown', got {data.chunking_strategy!r}",
        )

    scanner = KnowledgePackageScanner()
    scan_request = PackageScanRequest(
        package_code=package_code,
        package_root=str(package_root),
        dry_run=True,
        include_drafts=data.include_drafts,
    )
    scan_result = scanner.scan(scan_request)

    doc_results: list[DevIngestDocumentResult] = []
    total_chunks = 0
    ready_count = 0
    rejected_count = 0

    for doc in scan_result.documents:
        fm = doc.frontmatter or {}
        ingest_status = fm.get("ingestion_status", "")
        doc_status = fm.get("status", "")
        node_path = fm.get("node_path")

        gate = check_document_ingestion_readiness(fm, doc.relative_path)

        chunk_count = 0
        if gate.ready and doc.candidate_for_ingestion:
            try:
                raw = doc.path.read_bytes()
                chunks = chunk_markdown(raw.decode("utf-8"))
                chunk_count = len(chunks)
                total_chunks += chunk_count
            except Exception:
                pass

        if gate.ready:
            ready_count += 1
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
