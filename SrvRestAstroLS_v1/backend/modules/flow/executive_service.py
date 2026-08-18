"""Read-only executive case query service for Directorio."""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .audit_repository import FlowAuditRepository, sha256_of_snapshot
from .closure_repository import FlowClosurePostgresRepository
from .domain import AUDIT_SCHEMA_VERSION, FlowRequestNotFoundError
from .executive_ai import ExecutiveInterpreterPort
from .executive_query import (
    AUDIT_SNAPSHOT,
    LIVE,
    augment_metrics,
    build_executive_view,
)


class FlowAuditIntegrityError(RuntimeError):
    """Raised when the stored audit record cannot be trusted.

    This is a read-side integrity gate: the canonical snapshot is hash-checked
    and the schema version is validated before anything is served. A RESOLVED
    case without an audit record is also treated as an integrity anomaly
    instead of silently rebuilding a snapshot from live tables.
    """


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

    def _verified_snapshot(self, audit: dict[str, Any]) -> dict[str, Any]:
        if audit["schema_version"] != AUDIT_SCHEMA_VERSION:
            raise FlowAuditIntegrityError(
                f"unsupported audit schema version: {audit['schema_version']}"
            )
        recomputed = sha256_of_snapshot(audit["snapshot_jsonb"])
        if recomputed != audit["snapshot_sha256"]:
            raise FlowAuditIntegrityError(
                "audit snapshot hash mismatch: stored and canonical snapshots differ"
            )
        return audit["snapshot_jsonb"]

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
                if audit is None:
                    raise FlowAuditIntegrityError(
                        "resolved case missing audit record"
                    )

            if audit is not None:
                snapshot = self._verified_snapshot(audit)
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
                try:
                    view["executive_summary"] = self._interpreter.interpret(
                        question, view
                    )
                except Exception:
                    # The LLM is an optional layer over the structured facts.
                    # A provider failure must never take down the executive
                    # read model: the facts remain authoritative and the UI
                    # stays usable with the structured evidence.
                    view["executive_summary"] = None
            return view
