"""Read-only PostgreSQL repository for the executive Flow case list."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection

from modules.db.transaction import fetch_all


class FlowExecutiveListPostgresRepository:
    """Fetch summary rows without loading the full executive detail model."""

    async def list_cases(
        self,
        conn: AsyncConnection,
        *,
        statuses: Sequence[str] | None,
        sector_id: str | None,
        search: str | None,
        sla_status: str | None,
        escalated: bool | None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
        }

        if statuses:
            where.append("fr.status = any(%(statuses)s::text[])")
            params["statuses"] = list(statuses)
        if sector_id:
            where.append("cr.sector_id = %(sector_id)s")
            params["sector_id"] = sector_id
        if search:
            where.append(
                """
                (
                    fr.id::text ilike %(search)s escape '\\'
                    or fr.conversation_id::text ilike %(search)s escape '\\'
                    or coalesce(fr.tentative_category, '') ilike %(search)s escape '\\'
                    or coalesce(fr.description, '') ilike %(search)s escape '\\'
                    or coalesce(fr.location_text, '') ilike %(search)s escape '\\'
                    or coalesce(cr.sector_name, '') ilike %(search)s escape '\\'
                )
                """
            )
            params["search"] = f"%{_escape_like(search)}%"
        if sla_status:
            where.append("current_sla.status = %(sla_status)s")
            params["sla_status"] = sla_status
        if escalated is True:
            where.append("coalesce(escalation_summary.escalation_count, 0) > 0")
        elif escalated is False:
            where.append("coalesce(escalation_summary.escalation_count, 0) = 0")

        where_sql = "where " + " and ".join(where) if where else ""
        return await fetch_all(
            conn,
            f"""
            with current_routing as (
                select distinct on (frr.request_id)
                       frr.request_id,
                       frr.id::text as routing_id,
                       frr.sector_id,
                       fsec.display_name as sector_name,
                       frr.level::int as current_level,
                       frr.destination as current_destination,
                       frr.status as routing_status,
                       frr.assigned_at_utc,
                       fws.operational_status as work_status,
                       fws.first_response_at_utc,
                       fws.first_responder
                from flow_request_routings frr
                join flow_sectors fsec on fsec.sector_id = frr.sector_id
                left join flow_request_work_states fws on fws.routing_id = frr.id
                where frr.status = 'ASSIGNED'
                order by frr.request_id, frr.level desc, frr.assigned_at_utc desc,
                         frr.id desc
            ),
            current_sla as (
                select distinct on (fs.routing_id)
                       fs.routing_id,
                       fs.status,
                       fs.due_at_utc,
                       fs.started_at_utc,
                       fs.breached_at_utc,
                       fs.met_at_utc
                from flow_request_slas fs
                order by fs.routing_id, fs.started_at_utc desc, fs.id desc
            ),
            any_sla as (
                select fs.request_id,
                       bool_or(fs.status = 'BREACHED') as has_breached_sla
                from flow_request_slas fs
                group by fs.request_id
            ),
            escalation_summary as (
                select fe.request_id,
                       count(*)::int as escalation_count,
                       max(fe.created_at_utc) as last_escalation_at
                from flow_request_escalations fe
                group by fe.request_id
            ),
            resolution_summary as (
                select frs.request_id,
                       max(frs.proposed_at_utc) as last_resolution_at
                from flow_request_resolutions frs
                group by frs.request_id
            ),
            approval_summary as (
                select fca.request_id,
                       max(fca.updated_at_utc) as last_approval_at
                from flow_closure_approvals fca
                group by fca.request_id
            )
            select
                fr.id::text as request_id,
                fr.conversation_id::text as conversation_id,
                fr.status,
                case
                    when fr.status = 'RESOLVED' then 'closed'
                    when fr.status = 'RESOLUTION_PENDING_APPROVAL' then 'pending_approval'
                    else 'open'
                end as status_fact,
                case
                    when fr.status = 'RESOLVED'
                     and exists (
                         select 1 from flow_case_audit_records fcar
                         where fcar.request_id = fr.id
                     ) then 'AUDIT_SNAPSHOT'
                    else 'LIVE'
                end as data_source,
                coalesce(cr.sector_id, null) as sector_id,
                coalesce(cr.sector_name, null) as sector_name,
                fr.tentative_category as category,
                fr.description,
                fr.location_text as location,
                received.received_at,
                fr.confirmed_at_utc as confirmed_at,
                cr.routing_id as current_routing_id,
                cr.current_level,
                cr.current_destination,
                cr.routing_status as current_routing_status,
                cr.work_status as current_work_status,
                coalesce(current_sla.status, null) as sla_status,
                current_sla.due_at_utc as sla_due_at,
                coalesce(any_sla.has_breached_sla, false) as has_breached_sla,
                cr.first_response_at_utc as first_response_at,
                fr.resolved_at_utc as resolved_at,
                coalesce(escalation_summary.escalation_count, 0) as escalation_count,
                greatest(
                    coalesce(fr.confirmed_at_utc, '-infinity'::timestamptz),
                    coalesce(fr.resolved_at_utc, '-infinity'::timestamptz),
                    coalesce(cr.assigned_at_utc, '-infinity'::timestamptz),
                    coalesce(escalation_summary.last_escalation_at, '-infinity'::timestamptz),
                    coalesce(resolution_summary.last_resolution_at, '-infinity'::timestamptz),
                    coalesce(approval_summary.last_approval_at, '-infinity'::timestamptz)
                ) as updated_at,
                count(*) over ()::int as total_count
            from flow_requests fr
            left join current_routing cr on cr.request_id = fr.id
            left join current_sla on current_sla.routing_id = cr.routing_id::uuid
            left join any_sla on any_sla.request_id = fr.id
            left join escalation_summary on escalation_summary.request_id = fr.id
            left join resolution_summary on resolution_summary.request_id = fr.id
            left join approval_summary on approval_summary.request_id = fr.id
            left join lateral (
                select min(fm.occurred_at_utc) as received_at
                from flow_messages fm
                where fm.conversation_id = fr.conversation_id
                  and fm.direction = 'inbound'
            ) received on true
            {where_sql}
            order by updated_at desc, fr.id desc
            offset %(offset)s
            limit %(limit)s
            """,
            params,
        )

    async def list_sector_options(self, conn: AsyncConnection) -> list[dict[str, str]]:
        return await fetch_all(
            conn,
            """
            select sector_id, display_name
            from flow_sectors
            where active = true
            order by display_name, sector_id
            """,
        )


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards while keeping search a simple substring query."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
