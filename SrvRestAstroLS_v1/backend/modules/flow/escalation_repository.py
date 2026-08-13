"""PostgreSQL persistence for deterministic Flow escalations."""

from __future__ import annotations

from psycopg import AsyncConnection

from modules.db.transaction import fetch_all, fetch_one

from .domain import (
    FIRST_RESPONSE_SLA_BREACHED,
    EscalationCandidate,
    EscalationStatus,
    FlowEscalation,
)


def _candidate(row: dict) -> EscalationCandidate:
    return EscalationCandidate(**row)


def _escalation(row: dict | None) -> FlowEscalation | None:
    if row is None:
        return None
    return FlowEscalation(
        id=row["id"],
        request_id=row["request_id"],
        sector_id=row["sector_id"],
        from_routing_id=row["from_routing_id"],
        from_level=int(row["from_level"]),
        trigger_sla_id=row["trigger_sla_id"],
        to_level=int(row["to_level"]),
        to_routing_id=row["to_routing_id"],
        status=EscalationStatus(row["status"]),
        created_at=row["created_at_utc"],
        completed_at=row["completed_at_utc"],
        last_error_code=row["last_error_code"],
    )


_ESCALATION_COLUMNS = """
    id::text, request_id::text, sector_id, from_routing_id::text,
    from_level, trigger_sla_id::text, to_level, to_routing_id::text,
    status, created_at_utc, completed_at_utc, last_error_code
"""

_CANDIDATE_QUERY = """
    select fr.id::text as request_id, fr.description, fr.location_text,
           fc.channel as origin_channel, frr.sector_id,
           fsec.display_name as sector_display_name,
           frr.id::text as from_routing_id, frr.level as from_level,
           frr.destination as from_destination,
           frr.assigned_at_utc as from_assigned_at,
           fs.id::text as trigger_sla_id, fs.due_at_utc as sla_due_at,
           fs.status as sla_status,
           fws.first_response_at_utc as first_response_at
    from flow_request_slas fs
    join flow_request_routings frr on frr.id = fs.routing_id
    join flow_requests fr on fr.id = frr.request_id
    join flow_conversations fc on fc.id = fr.conversation_id
    join flow_sectors fsec on fsec.sector_id = frr.sector_id
    left join flow_request_work_states fws on fws.routing_id = frr.id
    where fs.sla_type = 'FIRST_RESPONSE'
      and fs.status = 'BREACHED'
      and frr.status = 'ASSIGNED'
      and fr.status = 'CONFIRMED'
      and (fws.first_response_at_utc is null
           or fws.first_response_at_utc > fs.due_at_utc)
      and exists (
          select 1
          from flow_sector_levels next_level
          where next_level.sector_id = frr.sector_id
            and next_level.level > frr.level
            and next_level.active = true
      )
      and not exists (
          select 1 from flow_request_escalations fe
          where fe.trigger_sla_id = fs.id
            and fe.trigger_type = 'FIRST_RESPONSE_SLA_BREACHED'
            and fe.status = 'COMPLETED'
      )
"""


class FlowEscalationPostgresRepository:
    async def list_eligible(self, conn: AsyncConnection) -> tuple[EscalationCandidate, ...]:
        rows = await fetch_all(
            conn,
            _CANDIDATE_QUERY + " order by fs.breached_at_utc, fs.id",
        )
        return tuple(_candidate(row) for row in rows)

    async def get_eligible(
        self, conn: AsyncConnection, trigger_sla_id: str
    ) -> EscalationCandidate | None:
        row = await fetch_one(
            conn,
            _CANDIDATE_QUERY
            + " and fs.id = %(sla_id)s for update of fs, frr",
            {"sla_id": trigger_sla_id},
        )
        return _candidate(row) if row else None

    async def get_by_trigger(
        self, conn: AsyncConnection, trigger_sla_id: str
    ) -> FlowEscalation | None:
        return _escalation(
            await fetch_one(
                conn,
                f"""
                select {_ESCALATION_COLUMNS}
                from flow_request_escalations
                where trigger_sla_id = %(sla_id)s
                  and trigger_type = %(trigger_type)s
                for update
                """,
                {
                    "sla_id": trigger_sla_id,
                    "trigger_type": FIRST_RESPONSE_SLA_BREACHED,
                },
            )
        )

    async def create_pending(
        self,
        conn: AsyncConnection,
        candidate: EscalationCandidate,
        *,
        to_level: int,
    ) -> FlowEscalation:
        row = await fetch_one(
            conn,
            f"""
            insert into flow_request_escalations (
                request_id, sector_id, from_routing_id, from_level,
                trigger_type, trigger_sla_id, to_level
            ) values (
                %(request_id)s, %(sector_id)s, %(from_routing_id)s,
                %(from_level)s, %(trigger_type)s, %(trigger_sla_id)s,
                %(to_level)s
            )
            on conflict (trigger_sla_id, trigger_type) do nothing
            returning {_ESCALATION_COLUMNS}
            """,
            {
                "request_id": candidate.request_id,
                "sector_id": candidate.sector_id,
                "from_routing_id": candidate.from_routing_id,
                "from_level": candidate.from_level,
                "trigger_type": FIRST_RESPONSE_SLA_BREACHED,
                "trigger_sla_id": candidate.trigger_sla_id,
                "to_level": to_level,
            },
        )
        created = _escalation(row)
        if created:
            return created
        existing = await self.get_by_trigger(conn, candidate.trigger_sla_id)
        if existing is None:
            raise RuntimeError("Escalation conflict returned no row.")
        return existing

    async def mark_completed(
        self, conn: AsyncConnection, *, escalation_id: str, to_routing_id: str
    ) -> FlowEscalation:
        row = await fetch_one(
            conn,
            f"""
            update flow_request_escalations
            set to_routing_id = %(routing_id)s, status = 'COMPLETED',
                completed_at_utc = coalesce(completed_at_utc, now()),
                last_error_code = null, last_error_detail = null,
                updated_at_utc = now()
            where id = %(id)s
            returning {_ESCALATION_COLUMNS}
            """,
            {"id": escalation_id, "routing_id": to_routing_id},
        )
        result = _escalation(row)
        if result is None:
            raise RuntimeError("Escalation completion returned no row.")
        return result

    async def mark_failed(
        self, conn: AsyncConnection, *, escalation_id: str, error_code: str
    ) -> FlowEscalation:
        row = await fetch_one(
            conn,
            f"""
            update flow_request_escalations
            set status = 'FAILED', last_error_code = %(error_code)s,
                last_error_detail = 'Next-level delivery was not completed safely.',
                completed_at_utc = null, updated_at_utc = now()
            where id = %(id)s
            returning {_ESCALATION_COLUMNS}
            """,
            {"id": escalation_id, "error_code": error_code},
        )
        result = _escalation(row)
        if result is None:
            raise RuntimeError("Escalation failure returned no row.")
        return result

    async def evidence(self, conn: AsyncConnection, escalation_id: str) -> dict | None:
        return await fetch_one(
            conn,
            """
            select fe.id::text as escalation_id, fe.request_id::text,
                   fe.sector_id, fe.from_routing_id::text, fe.from_level,
                   fe.trigger_type, fe.trigger_sla_id::text, fe.to_level,
                   fe.to_routing_id::text, fe.status, fe.created_at_utc,
                   fe.completed_at_utc, fe.last_error_code
            from flow_request_escalations fe
            where fe.id = %(id)s
            """,
            {"id": escalation_id},
        )
