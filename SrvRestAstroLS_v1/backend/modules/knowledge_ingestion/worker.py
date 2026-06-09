"""Knowledge Ingestion Worker — Phase 1 skeleton.

This worker implements the ingestion pipeline phases defined in
the design document (SrvRestAstroLS_v1/docs/knowledge_ingestion_multiscope_design_20260607.md).

Phase 1 provides the structural skeleton only:
  - Metadata validation (Fase 1 of the design)
  - Ingestion run registration
  - Phase tracking
  - Package dry-run scan (Fase 1.2)
  - Package document persistence (Fase 1.3b)

Future phases will implement:
  - Convert to Markdown/text (Fase 2)
  - Generate L0/L1 if applicable (Fase 3-4)
  - Semantic chunk (Fase 5)
  - Save document/chunks (Fase 6)
  - Generate embeddings (Fase 7)
  - Index (Fase 8)
  - Register status/error (Fase 9)
"""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection

from modules.knowledge_ingestion.markdown_chunker import chunk_markdown


def _sanitize_metadata(val: Any) -> Any:
    """Convert non-JSON-serializable types (dates, etc.) to strings."""
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: _sanitize_metadata(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_metadata(v) for v in val]
    return val
from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
from modules.knowledge_ingestion.schemas import (
    INGESTION_PHASES,
    DocumentUpsertStatus,
    IngestionMetadata,
    KnowledgeDocumentPersistenceResult,
    PackagePersistResult,
    PackageScanRequest,
    PackageScanResult,
)


class KnowledgeIngestionWorker:
    """Generic ingestion worker for Team360 knowledge platform.

    This worker is not tied to any specific assistant, package or client.
    It receives validated metadata + source content and executes the
    ingestion pipeline.

    In Phase 1, only metadata validation and run tracking are implemented.
    """

    def __init__(self, repository: KnowledgeIngestionRepository | None = None) -> None:
        self.repository = repository or KnowledgeIngestionRepository()

    async def validate_and_register(
        self,
        conn: AsyncConnection,
        metadata: IngestionMetadata,
        document_source: str,
        worker_code: str = "knowledge_ingestion_worker",
        triggered_by_email: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        errors = metadata.validate()
        if errors:
            raise ValueError(
                f"Ingestion metadata validation failed: {'; '.join(errors)}"
            )

        phases_status: dict[str, str] = {
            "validate_metadata": "completed",
        }
        for phase in INGESTION_PHASES[1:]:
            phases_status[phase] = "pending"

        if dry_run:
            return {
                "run_id": None,
                "dry_run": True,
                "phases": phases_status,
            }

        context = await self.repository.resolve_ingestion_context(
            conn=conn,
            organization_code=metadata.organization_code,
            workspace_code=metadata.workspace_code,
            knowledge_scope_code=metadata.knowledge_scope_code,
            package_code=metadata.package_code or None,
            assistant_instance_code=metadata.assistant_instance_code or None,
            worker_code=worker_code,
            triggered_by_email=triggered_by_email,
        )

        metadata_snapshot = metadata.to_metadata_dict()
        if triggered_by_email:
            metadata_snapshot["triggered_by_email"] = triggered_by_email
        metadata_snapshot["ingestion_context"] = context.to_metadata_dict()

        run = await self.repository.create_ingestion_run(
            conn=conn,
            knowledge_scope_id=context.knowledge_scope_id,
            document_source=document_source,
            metadata_snapshot=metadata_snapshot,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            triggered_by_user_id=context.triggered_by_user_id,
        )

        await self.repository.update_ingestion_run_status(
            conn=conn,
            run_id=run["run_id"],
            status="running",
            phases_jsonb=phases_status,
        )

        return {
            "run_id": run["run_id"],
            "context": context,
            "phases": phases_status,
        }

    def validate_package_dry_run(
        self,
        package_code: str,
        package_root: str,
        *,
        include_drafts: bool = False,
        experimental: bool = False,
    ) -> PackageScanResult:
        scanner = KnowledgePackageScanner()
        request = PackageScanRequest(
            package_code=package_code,
            package_root=package_root,
            dry_run=True,
            include_drafts=include_drafts,
            experimental=experimental,
        )
        return scanner.scan(request)

    async def persist_package_documents(
        self,
        conn: AsyncConnection,
        *,
        organization_code: str,
        workspace_code: str,
        knowledge_scope_code: str,
        package_code: str,
        package_root: str,
        assistant_instance_code: str | None = None,
        triggered_by_email: str | None = None,
        dry_run: bool = True,
        include_chunks: bool = False,
    ) -> PackagePersistResult:
        """Scan a package and persist approved candidates as KnowledgeDocuments.

        Phase 1.3b: persists document metadata only — no chunks, no embeddings.
        Phase 1.4a: include_chunks=True also generates structural Markdown chunks.
        """
        context = await self.repository.resolve_ingestion_context(
            conn=conn,
            organization_code=organization_code,
            workspace_code=workspace_code,
            knowledge_scope_code=knowledge_scope_code,
            package_code=package_code,
            assistant_instance_code=assistant_instance_code,
            worker_code="knowledge_ingestion_worker",
            triggered_by_email=triggered_by_email,
        )

        scanner = KnowledgePackageScanner()
        scan_request = PackageScanRequest(
            package_code=package_code,
            package_root=package_root,
            dry_run=True,
            include_drafts=False,
        )
        scan_result = scanner.scan(scan_request)

        doc_results: list[KnowledgeDocumentPersistenceResult] = []
        warnings: list[str] = list(scan_result.warnings)
        errors: list[str] = list(scan_result.errors)

        est_chunk_count = 0
        if dry_run:
            if include_chunks:
                for doc in scan_result.documents:
                    if doc.valid and doc.candidate_for_ingestion:
                        try:
                            raw = doc.path.read_bytes()
                            chunks = chunk_markdown(raw.decode("utf-8"))
                            est_chunk_count += len(chunks)
                        except Exception:
                            pass
            return PackagePersistResult(
                package_code=package_code,
                package_root=package_root,
                scanned_count=scan_result.scanned_count,
                candidate_count=scan_result.candidate_count,
                persisted_count=0,
                inserted_count=0,
                updated_count=0,
                unchanged_count=0,
                skipped_count=0,
                invalid_count=0,
                documents=doc_results,
                warnings=warnings,
                errors=errors,
                run_id=None,
                total_chunk_count=est_chunk_count,
            )

        phases_status: dict[str, str] = {
            "validate_metadata": "completed",
        }
        for phase in INGESTION_PHASES[1:]:
            phases_status[phase] = "pending"

        run = await self.repository.create_ingestion_run(
            conn=conn,
            knowledge_scope_id=context.knowledge_scope_id,
            document_source=f"package:{package_code}",
            metadata_snapshot={
                "package_code": package_code,
                "organization_code": organization_code,
                "workspace_code": workspace_code,
                "knowledge_scope_code": knowledge_scope_code,
                "assistant_instance_code": assistant_instance_code,
            },
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            triggered_by_user_id=context.triggered_by_user_id,
        )
        run_id = run["run_id"]

        await self.repository.update_ingestion_run_status(
            conn=conn,
            run_id=run_id,
            status="running",
            phases_jsonb=phases_status,
        )

        inserted_count = 0
        updated_count = 0
        unchanged_count = 0
        skipped_count = 0
        invalid_count = 0
        persist_failed = False

        for doc in scan_result.documents:
            if doc.issues:
                has_errors = any(i.severity == "error" for i in doc.issues)
            else:
                has_errors = False

            if not doc.valid or not doc.candidate_for_ingestion:
                doc_results.append(KnowledgeDocumentPersistenceResult(
                    relative_path=doc.relative_path,
                    status=DocumentUpsertStatus.SKIPPED,
                    action="skipped",
                    warnings=[i.message for i in doc.issues if i.severity == "warning"],
                    errors=[i.message for i in doc.issues] if has_errors else [],
                ))
                if has_errors:
                    invalid_count += 1
                else:
                    skipped_count += 1
                continue

            fm = doc.frontmatter or {}
            source_uri = doc.relative_path
            if not source_uri:
                doc_results.append(KnowledgeDocumentPersistenceResult(
                    relative_path=doc.relative_path,
                    status=DocumentUpsertStatus.INVALID,
                    action="skipped",
                    errors=["source_uri is empty or missing"],
                ))
                invalid_count += 1
                continue

            source_type = fm.get("source_type", "markdown")
            title = fm.get("title", "") or Path(doc.relative_path).stem

            try:
                raw_bytes = doc.path.read_bytes()
                content_hash = hashlib.sha256(raw_bytes).hexdigest()
            except Exception as exc:
                doc_results.append(KnowledgeDocumentPersistenceResult(
                    relative_path=doc.relative_path,
                    status=DocumentUpsertStatus.INVALID,
                    action="skipped",
                    errors=[f"Failed to read file for content_hash: {exc}"],
                ))
                invalid_count += 1
                continue

            metadata_payload = dict(fm)
            metadata_payload["content_hash"] = content_hash
            metadata_payload["scanner_valid"] = doc.valid
            metadata_payload["scanner_candidate"] = doc.candidate_for_ingestion
            metadata_payload = _sanitize_metadata(metadata_payload)

            node_path = fm.get("node_path")

            try:
                doc_id, action = await self.repository.upsert_knowledge_document(
                    conn=conn,
                    knowledge_scope_id=context.knowledge_scope_id,
                    source_type=source_type,
                    source_uri=source_uri,
                    title=title,
                    content_hash=content_hash,
                    metadata_jsonb=metadata_payload,
                    node_path=node_path,
                )
            except Exception as exc:
                persist_failed = True
                doc_results.append(KnowledgeDocumentPersistenceResult(
                    relative_path=doc.relative_path,
                    status=DocumentUpsertStatus.INVALID,
                    action="failed",
                    errors=[f"Upsert failed: {exc}"],
                ))
                invalid_count += 1
                continue

            if action == "inserted":
                inserted_count += 1
            elif action == "updated":
                updated_count += 1
            else:
                unchanged_count += 1

            doc_chunk_count = 0
            if include_chunks and action in ("inserted", "updated"):
                try:
                    raw_bytes = doc.path.read_bytes()
                    chunks = chunk_markdown(
                        raw_bytes.decode("utf-8"),
                        base_metadata={
                            "document_id": doc_id,
                            "relative_path": doc.relative_path,
                            "knowledge_scope_code": knowledge_scope_code,
                            "package_code": package_code,
                            "assistant_instance_code": assistant_instance_code or "",
                            "organization_code": organization_code,
                            "workspace_code": workspace_code,
                            "node_path": node_path or "",
                            "access_tags": fm.get("access_tags", []),
                            "document_type": fm.get("document_type", ""),
                            "locale": fm.get("locale", ""),
                            "source_section": doc.source_section,
                        },
                    )
                except Exception as exc:
                    persist_failed = True
                    doc_results.append(KnowledgeDocumentPersistenceResult(
                        relative_path=doc.relative_path,
                        status=DocumentUpsertStatus.INVALID,
                        document_id=doc_id,
                        action="chunk_failed",
                        errors=[f"Chunking failed: {exc}"],
                    ))
                    invalid_count += 1
                    continue

                chunk_rows = []
                for c in chunks:
                    chunk_meta = _sanitize_metadata(dict(c.metadata))
                    chunk_meta["document_source_uri"] = doc.relative_path
                    chunk_meta["content_hash"] = c.content_hash
                    chunk_meta["heading_path"] = list(c.heading_path)
                    chunk_meta["heading_level"] = c.heading_level
                    chunk_rows.append({
                        "chunk_index": c.chunk_index,
                        "title": c.title,
                        "content": c.content,
                        "metadata_jsonb": chunk_meta,
                        "token_count": None,
                        "node_path": node_path,
                        "permission_tags": fm.get("access_tags", []),
                    })

                try:
                    actual = await self.repository.replace_chunks_for_document(
                        conn=conn,
                        document_id=doc_id,
                        chunks=chunk_rows,
                    )
                    doc_chunk_count = actual
                except Exception as exc:
                    persist_failed = True
                    doc_results.append(KnowledgeDocumentPersistenceResult(
                        relative_path=doc.relative_path,
                        status=DocumentUpsertStatus.INVALID,
                        document_id=doc_id,
                        action="chunk_replace_failed",
                        errors=[f"Chunk replacement failed: {exc}"],
                    ))
                    invalid_count += 1
                    continue

            doc_results.append(KnowledgeDocumentPersistenceResult(
                relative_path=doc.relative_path,
                status=action,
                document_id=doc_id,
                action=action,
                chunk_count=doc_chunk_count,
            ))

        persisted_count = inserted_count + updated_count
        total_chunk_count = sum(d.chunk_count for d in doc_results)

        if persist_failed:
            await self.repository.update_ingestion_run_status(
                conn=conn,
                run_id=run_id,
                status="failed",
                error_code="PERSIST_ERROR",
                error_detail="One or more document upserts or chunk replacements failed",
            )
        else:
            phases_status["save_document_chunks"] = "completed"
            await self.repository.update_ingestion_run_status(
                conn=conn,
                run_id=run_id,
                status="completed",
                phases_jsonb=phases_status,
                chunk_count=total_chunk_count,
                token_count=0,
            )

        return PackagePersistResult(
            package_code=package_code,
            package_root=package_root,
            scanned_count=scan_result.scanned_count,
            candidate_count=scan_result.candidate_count,
            persisted_count=persisted_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            skipped_count=skipped_count,
            invalid_count=invalid_count,
            documents=doc_results,
            warnings=warnings,
            errors=errors,
            run_id=run_id,
            total_chunk_count=total_chunk_count,
        )

    async def advance_phase(
        self,
        conn: AsyncConnection,
        run_id: str,
        current_phase: str,
        next_phase: str,
        phases_jsonb: dict[str, str],
    ) -> None:
        """Advance the ingestion pipeline to the next phase.

        To be implemented in Phase 2+ with chunk/embed/index logic.
        Currently a structural stub that validates phase ordering.
        """
        if phases_jsonb.get(current_phase) != "completed":
            raise ValueError(
                f"Cannot advance from {current_phase}: phase not completed"
            )
        if current_phase not in INGESTION_PHASES:
            raise ValueError(f"Unknown current phase: {current_phase}")
        if next_phase not in INGESTION_PHASES:
            raise ValueError(f"Unknown next phase: {next_phase}")
        current_idx = INGESTION_PHASES.index(current_phase)
        next_idx = INGESTION_PHASES.index(next_phase)
        if next_idx != current_idx + 1:
            raise ValueError(
                f"Cannot jump from {current_phase} (index {current_idx}) "
                f"to {next_phase} (index {next_idx})"
            )
