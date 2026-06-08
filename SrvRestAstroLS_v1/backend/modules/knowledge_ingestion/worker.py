"""Knowledge Ingestion Worker — Phase 1 skeleton.

This worker implements the ingestion pipeline phases defined in
the design document (SrvRestAstroLS_v1/docs/knowledge_ingestion_multiscope_design_20260607.md).

Phase 1 provides the structural skeleton only:
  - Metadata validation (Fase 1 of the design)
  - Ingestion run registration
  - Phase tracking
  - Package dry-run scan (Fase 1.2)

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

from typing import Any

from psycopg import AsyncConnection

from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
from modules.knowledge_ingestion.schemas import (
    INGESTION_PHASES,
    IngestionMetadata,
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
