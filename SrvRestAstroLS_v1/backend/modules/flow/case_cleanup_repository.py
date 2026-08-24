"""Transactional deletion of Flow case data.

Case data is deliberately separated from the intake history that provides
Gmail idempotency.  Flow configuration, scheduler state, Gmail data, Diagnosis
and other modules are outside the deletion scope.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_one


FLOW_INTAKE_HISTORY_TABLES: tuple[str, ...] = (
    "flow_conversations",
    "flow_messages",
)

FLOW_CASE_TABLES: tuple[str, ...] = (
    "flow_interpretations",
    "flow_request_candidates",
    "flow_requests",
    "flow_request_routings",
    "flow_request_work_states",
    "flow_request_operational_events",
    "flow_request_slas",
    "flow_request_sla_events",
    "flow_request_escalations",
    "flow_request_resolutions",
    "flow_closure_approvals",
    "flow_case_audit_records",
    "flow_citizen_notifications",
)

# Deletion order follows the audited FK graph.  The request/approval cycle is
# broken inside the same transaction by clearing the nullable authorization FK
# while the resolution guard and its matching evidence check are disabled
# locally for that table only.  Both are restored before commit.
_DELETE_ORDER: tuple[str, ...] = (
    "flow_citizen_notifications",
    "flow_case_audit_records",
    "flow_closure_approvals",
    "flow_request_resolutions",
    "flow_request_escalations",
    "flow_request_operational_events",
    "flow_request_sla_events",
    "flow_request_slas",
    "flow_request_work_states",
    "flow_request_routings",
    "flow_requests",
    "flow_request_candidates",
    "flow_interpretations",
)

_RESOLUTION_GUARD = "trg_flow_request_resolution_guard"
_RESOLUTION_EVIDENCE_CHECK = "chk_flow_request_resolution_evidence"


class FlowCaseCleanupPostgresRepository:
    """SQL for clearing cases while preserving intake idempotency history."""

    async def clear_cases(self, conn: AsyncConnection) -> dict[str, Any]:
        preserved_before: dict[str, int] = {}
        for table in FLOW_INTAKE_HISTORY_TABLES:
            row = await fetch_one(conn, f"select count(*)::int as count from {table}")
            preserved_before[table] = int(row["count"] if row else 0)

        before: dict[str, int] = {}
        for table in FLOW_CASE_TABLES:
            row = await fetch_one(conn, f"select count(*)::int as count from {table}")
            before[table] = int(row["count"] if row else 0)

        # A resolved request points to its approved closure row while that row
        # points back to the request.  This is a narrow, transactional trigger
        # pause used only to clear the nullable cycle-breaking FK.  The trigger
        # is explicitly enabled again before this transaction can commit.
        if before["flow_requests"]:
            await execute(
                conn,
                "alter table flow_requests drop constraint "
                f"{_RESOLUTION_EVIDENCE_CHECK}",
            )
            await execute(
                conn,
                f"alter table flow_requests disable trigger {_RESOLUTION_GUARD}",
            )
            await execute(
                conn,
                "update flow_requests set authorized_approval_id = null "
                "where authorized_approval_id is not null",
            )

        deleted: dict[str, int] = {}
        for table in _DELETE_ORDER:
            count = await execute(conn, f"delete from {table}")
            deleted[table] = int(count or 0)

        if before["flow_requests"]:
            await execute(
                conn,
                f"alter table flow_requests enable trigger {_RESOLUTION_GUARD}",
            )
            await execute(
                conn,
                "alter table flow_requests add constraint "
                f"{_RESOLUTION_EVIDENCE_CHECK} check ("
                "status <> 'RESOLVED' or ("
                "resolved_at_utc is not null and authorized_by is not null "
                "and authorized_approval_id is not null))",
            )

        after: dict[str, int] = {}
        for table in FLOW_CASE_TABLES:
            row = await fetch_one(conn, f"select count(*)::int as count from {table}")
            after[table] = int(row["count"] if row else 0)

        preserved_after: dict[str, int] = {}
        for table in FLOW_INTAKE_HISTORY_TABLES:
            row = await fetch_one(conn, f"select count(*)::int as count from {table}")
            preserved_after[table] = int(row["count"] if row else 0)

        return {
            "status": "cleared",
            "tables": FLOW_CASE_TABLES,
            "preserved_tables": FLOW_INTAKE_HISTORY_TABLES,
            "before": before,
            "deleted": deleted,
            "after": after,
            "preserved_before": preserved_before,
            "preserved_after": preserved_after,
            "cases_before": before["flow_requests"],
            "cases_after": after["flow_requests"],
        }
