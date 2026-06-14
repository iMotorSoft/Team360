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

Scope hardening (Fase 1.4):
  - organization_code, workspace_code, knowledge_scope_code required for
    persist mode; optional in dry_run.
  - Request codes must match frontmatter codes on ready documents.
  - Forbidden technical identifiers (vera_*) rejected.
  - access_tags required for persist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    SOURCE_TYPES,
    check_document_ingestion_readiness,
)
from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker


# ── Constants ────────────────────────────────────────────────────────────────

FORBIDDEN_TECHNICAL_PREFIXES = ("vera_",)

ALLOWED_SOURCE_TYPES = frozenset(SOURCE_TYPES)


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
    scope_errors: list[str] = Field(default_factory=list)


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
    scope_warnings: list[str] = Field(default_factory=list)
    scope_errors: list[str] = Field(default_factory=list)
    run_id: str | None = None
    persisted_document_count: int = 0
    persisted_chunk_count: int = 0
    requested_by: str = "dev_internal"


class DevIngestRequest(BaseModel):
    package_code: str
    package_path: str
    mode: str = "dry_run"
    include_drafts: bool = False
    chunking_strategy: str = "markdown"
    organization_code: str = ""
    workspace_code: str = ""
    knowledge_scope_code: str = ""
    requested_by: str = "dev_internal"
    source_type: str = "markdown"


# ── Validation helpers ──────────────────────────────────────────────────────


def _reject_empty(value: str, name: str) -> None:
    if not value or not value.strip():
        raise HTTPException(
            status_code=422,
            detail=f"{name} is required",
        )


def _reject_forbidden_technical_id(value: str, name: str) -> None:
    stripped = value.strip().lower()
    for prefix in FORBIDDEN_TECHNICAL_PREFIXES:
        if stripped.startswith(prefix):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{name} must not use forbidden technical prefix "
                    f"'{prefix}': got {value!r}"
                ),
            )


def _validate_scope_codes(
    data: DevIngestRequest,
    mode: str,
) -> list[str]:
    warnings: list[str] = []

    if mode == "persist":
        _reject_empty(data.organization_code, "organization_code")
        _reject_empty(data.workspace_code, "workspace_code")
        _reject_empty(data.knowledge_scope_code, "knowledge_scope_code")

    for field, name in [
        (data.organization_code, "organization_code"),
        (data.workspace_code, "workspace_code"),
        (data.knowledge_scope_code, "knowledge_scope_code"),
        (data.package_code, "package_code"),
    ]:
        if field and field.strip():
            _reject_forbidden_technical_id(field, name)

    if data.source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}, "
                f"got {data.source_type!r}"
            ),
        )

    return warnings


def _check_document_scope_consistency(
    doc_index: int,
    relative_path: str,
    frontmatter: dict[str, Any],
    request_org: str,
    request_ws: str,
    request_ks: str,
    request_pkg: str,
) -> list[str]:
    errors: list[str] = []

    fm_org = (frontmatter.get("organization_code") or "").strip()
    fm_ws = (frontmatter.get("workspace_code") or "").strip()
    fm_ks = (frontmatter.get("knowledge_scope_code") or "").strip()
    fm_pkg = (frontmatter.get("package_code") or "").strip()

    if request_org and fm_org and request_org != fm_org:
        errors.append(f"organization_code mismatch: request={request_org!r}, doc={fm_org!r}")
    if request_ws and fm_ws and request_ws != fm_ws:
        errors.append(f"workspace_code mismatch: request={request_ws!r}, doc={fm_ws!r}")
    if request_ks and fm_ks and request_ks != fm_ks:
        errors.append(f"knowledge_scope_code mismatch: request={request_ks!r}, doc={fm_ks!r}")
    if request_pkg and fm_pkg and request_pkg != fm_pkg:
        errors.append(f"package_code mismatch: request={request_pkg!r}, doc={fm_pkg!r}")

    return errors


def _check_access_tags(frontmatter: dict[str, Any], relative_path: str) -> list[str]:
    errors: list[str] = []
    tags = frontmatter.get("access_tags")
    if not tags or not isinstance(tags, list) or len(tags) == 0:
        errors.append(f"access_tags missing or empty in document {relative_path}")
    return errors


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

    # ── Validate scope codes ─────────────────────────────────────────────
    scope_validation_warnings = _validate_scope_codes(data, mode)

    # ── Scan package (shared between modes) ──────────────────────────────

    scanner = KnowledgePackageScanner()
    scan_request = PackageScanRequest(
        package_code=package_code,
        package_root=str(package_root),
        dry_run=True,
        include_drafts=data.include_drafts,
    )
    scan_result = scanner.scan(scan_request)

    # ── Per-document readiness gate + scope validation ───────────────────

    doc_results: list[DevIngestDocumentResult] = []
    total_chunks = 0
    ready_count = 0
    rejected_count = 0
    scope_errors_list: list[str] = []
    scope_warnings_list: list[str] = list(scope_validation_warnings)

    detected_org: str | None = data.organization_code.strip() if data.organization_code else None
    detected_ws: str | None = data.workspace_code.strip() if data.workspace_code else None
    detected_ks: str | None = data.knowledge_scope_code.strip() if data.knowledge_scope_code else None

    for doc in scan_result.documents:
        fm = doc.frontmatter or {}
        ingest_status = fm.get("ingestion_status", "")
        doc_status = fm.get("status", "")
        node_path = fm.get("node_path")

        gate = check_document_ingestion_readiness(fm, doc.relative_path)

        doc_scope_errors: list[str] = []
        if gate.ready and doc.candidate_for_ingestion and mode == "persist":
            doc_scope_errors = _check_document_scope_consistency(
                doc_index=0,
                relative_path=doc.relative_path,
                frontmatter=fm,
                request_org=detected_org or "",
                request_ws=detected_ws or "",
                request_ks=detected_ks or "",
                request_pkg=package_code,
            )
            scope_errors_list.extend(doc_scope_errors)

            tag_errors = _check_access_tags(fm, doc.relative_path)
            doc_scope_errors.extend(tag_errors)

        if gate.ready and doc.candidate_for_ingestion and mode == "dry_run":
            doc_scope_errors = _check_document_scope_consistency(
                doc_index=0,
                relative_path=doc.relative_path,
                frontmatter=fm,
                request_org=detected_org or "",
                request_ws=detected_ws or "",
                request_ks=detected_ks or "",
                request_pkg=package_code,
            )
            for e in doc_scope_errors:
                scope_warnings_list.append(f"[dry_run] {e} (scope mismatch)")

            tag_issues = _check_access_tags(fm, doc.relative_path)
            for e in tag_issues:
                scope_warnings_list.append(f"[dry_run] {e}")

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
                pass

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
            scope_errors=doc_scope_errors,
        ))

    # ── Persist mode ─────────────────────────────────────────────────────

    if mode == "persist":
        if not _is_db_configured():
            return DevIngestResponse(
                ok=False,
                mode="persist",
                package_code=package_code,
                errors=["persist mode requires a database connection: set TEAM360_DB_URL or equivalent"],
                scope_errors=scope_errors_list,
            )

        if scope_errors_list:
            return DevIngestResponse(
                ok=False,
                mode="persist",
                package_code=package_code,
                document_count=len(doc_results),
                candidate_count=scan_result.candidate_count,
                ready_count=ready_count,
                rejected_count=rejected_count,
                chunk_count=total_chunks,
                documents=doc_results,
                errors=["Scope validation failed: persist aborted"],
                scope_errors=scope_errors_list,
                scope_warnings=scope_warnings_list,
            )

        if not detected_org or not detected_ws or not detected_ks:
            return DevIngestResponse(
                ok=False,
                mode="persist",
                package_code=package_code,
                errors=[
                    "persist mode requires organization_code, workspace_code, "
                    "and knowledge_scope_code in request or frontmatter"
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
                scope_errors=scope_errors_list,
            )

        # Merge persist results into doc_results
        persist_by_path: dict[str, dict] = {}
        for pd in persist_data["persist_documents"]:
            persist_by_path[pd["relative_path"]] = pd

        for dr in doc_results:
            p = persist_by_path.get(dr.relative_path)
            if p is not None:
                dr.persisted = p["action"] in ("inserted", "updated")
                dr.document_id = p["document_id"]
                if p["action"] == "unchanged":
                    dr.persisted = True
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
            scope_warnings=scope_warnings_list,
            scope_errors=scope_errors_list,
            run_id=persist_data["run_id"],
            persisted_document_count=persist_data["persisted_document_count"],
            persisted_chunk_count=persist_data["persisted_chunk_count"],
            requested_by=data.requested_by or "dev_internal",
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
        scope_warnings=scope_warnings_list,
        scope_errors=scope_errors_list,
        requested_by=data.requested_by or "dev_internal",
    )
