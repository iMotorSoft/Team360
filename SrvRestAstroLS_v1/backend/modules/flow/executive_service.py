"""Read-only executive case query service for Directorio."""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .audit_repository import FlowAuditRepository
from .closure_repository import FlowClosurePostgresRepository
from .domain import FlowRequestNotFoundError
from .executive_ai import ExecutiveInterpreterPort
from .executive_query import (
    AUDIT_SNAPSHOT,
    LIVE,
    augment_metrics,
    build_executive_view,
)


class FlowExecutiveAuditService:
    """Answers executive queries over persisted Flow facts. Never mutates."""

    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        closure_repository: FlowClosurePostgresRepository,
        audit_repository: FlowAuditRepository,
        interpreter: ExecutiveInterpreterPort | None = None,
    ) -> None:
        self._pool = pool
        self._closure_repository = closure_repository
        self._audit_repository = audit_repository
        self._interpreter = interpreter

    async def query_case(
        self, request_id: str, *, question: str | None = None
    ) -> dict[str, Any]:
        async with transaction(self._pool) as conn:
            context = await self._closure_repository.get_request_context(
                conn, request_id
            )
            if context is None:
                raise FlowRequestNotFoundError(f"Flow request not found: {request_id}")
            status = context["status"]

            audit = None
            if status == "RESOLVED":
                audit = await self._audit_repository.get_record(conn, request_id)

            if audit is not None:
                snapshot = audit["snapshot_jsonb"]
                view = build_executive_view(
                    snapshot,
                    data_source=AUDIT_SNAPSHOT,
                    request_status=status,
                    audit={
                        "audit_record_id": audit["audit_record_id"],
                        "schema_version": audit["schema_version"],
                        "generated_at": audit["generated_at_utc"].isoformat()
                        if audit.get("generated_at_utc") is not None
                        else None,
                        "resolved_at": audit["resolved_at_utc"].isoformat()
                        if audit.get("resolved_at_utc") is not None
                        else None,
                        "snapshot_sha256": audit["snapshot_sha256"],
                    },
                )
            else:
                snapshot = await self._audit_repository.build_snapshot(
                    conn, request_id
                )
                view = build_executive_view(
                    snapshot,
                    data_source=LIVE,
                    request_status=status,
                )

            augment_metrics(view)

            if self._interpreter is not None and question:
                view["executive_summary"] = self._interpreter.interpret(
                    question, view
                )
            return view
