"""PostgreSQL persistence for first-response SLA snapshots and results."""

from __future__ import annotations

from datetime import datetime

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_all, fetch_one

from .domain import FirstResponseSLA, FirstResponseSLAStatus


_COLUMNS = """
    fs.id::text, fs.routing_id::text, fs.request_id::text,
    fs.duration_seconds, fs.started_at_utc, fs.due_at_utc, fs.status,
    fws.first_response_at_utc, fs.met_at_utc, fs.breached_at_utc,
    fs.evaluated_at_utc
"""


def _sla(row: dict) -> FirstResponseSLA:
    return FirstResponseSLA(
        id=row["id"],
        routing_id=row["routing_id"],
        request_id=row["request_id"],
        duration_seconds=int(row["duration_seconds"]),
        started_at=row["started_at_utc"],
        due_at=row["due_at_utc"],
        status=FirstResponseSLAStatus(row["status"]),
        first_response_at=row["first_response_at_utc"],
        met_at=row["met_at_utc"],
        breached_at=row["breached_at_utc"],
        evaluated_at=row["evaluated_at_utc"],
    )


class FlowSLARepository:
    async def list_evaluable(
        self, conn: AsyncConnection
    ) -> tuple[FirstResponseSLA, ...]:
        rows = await fetch_all(
            conn,
            f"""
            select {_COLUMNS}
            from flow_request_slas fs
            left join flow_request_work_states fws on fws.routing_id = fs.routing_id
            where fs.status = 'PENDING'
               or (
                    fs.status = 'BREACHED'
                    and fws.first_response_at_utc is not null
                    and fws.first_response_at_utc <= fs.due_at_utc
               )
            order by fs.started_at_utc, fs.id
            for update of fs
            """,
        )
        return tuple(_sla(row) for row in rows)

    async def persist_evaluation(
        self,
        conn: AsyncConnection,
        *,
        sla: FirstResponseSLA,
        status: FirstResponseSLAStatus,
        now: datetime,
        reconciled: bool,
    ) -> FirstResponseSLA:
        if status == sla.status and not reconciled:
            await execute(
                conn,
                """
                update flow_request_slas
                set evaluated_at_utc = greatest(evaluated_at_utc, %(now)s),
                    updated_at_utc = now()
                where id = %(id)s
                """,
                {"id": sla.id, "now": now},
            )
        elif status == FirstResponseSLAStatus.MET:
            await execute(
                conn,
                """
                update flow_request_slas
                set status = 'MET',
                    met_at_utc = %(first_response_at)s,
                    breached_at_utc = null,
                    evaluated_at_utc = %(now)s,
                    updated_at_utc = now()
                where id = %(id)s
                """,
                {
                    "id": sla.id,
                    "first_response_at": sla.first_response_at,
                    "now": now,
                },
            )
        else:
            await execute(
                conn,
                """
                update flow_request_slas
                set status = 'BREACHED',
                    breached_at_utc = coalesce(breached_at_utc, %(now)s),
                    evaluated_at_utc = %(now)s,
                    updated_at_utc = now()
                where id = %(id)s
                """,
                {"id": sla.id, "now": now},
            )

        event_type = None
        if reconciled:
            event_type = "SLA_RECONCILED"
        elif status != sla.status:
            event_type = "SLA_MET" if status == FirstResponseSLAStatus.MET else "SLA_BREACHED"
        if event_type:
            await execute(
                conn,
                """
                insert into flow_request_sla_events (
                    sla_id, event_type, occurred_at_utc, from_status, to_status
                ) values (%(sla_id)s, %(event_type)s, %(occurred_at)s,
                          %(from_status)s, %(to_status)s)
                on conflict (sla_id, event_type) do nothing
                """,
                {
                    "sla_id": sla.id,
                    "event_type": event_type,
                    "occurred_at": sla.first_response_at if status == FirstResponseSLAStatus.MET else now,
                    "from_status": sla.status.value,
                    "to_status": status.value,
                },
            )
        row = await fetch_one(
            conn,
            f"""
            select {_COLUMNS}
            from flow_request_slas fs
            left join flow_request_work_states fws on fws.routing_id = fs.routing_id
            where fs.id = %(id)s
            """,
            {"id": sla.id},
        )
        if row is None:
            raise RuntimeError("Flow SLA evaluation returned no row.")
        return _sla(row)

    async def evidence(self, conn: AsyncConnection, routing_id: str) -> dict | None:
        return await fetch_one(
            conn,
            """
            select fs.id::text as sla_id, fs.routing_id::text,
                   fs.request_id::text, fs.duration_seconds,
                   fs.started_at_utc, fs.due_at_utc, fs.status,
                   fws.operational_status, fws.first_response_at_utc,
                   fs.met_at_utc, fs.breached_at_utc, fs.evaluated_at_utc,
                   count(fse.id) as event_count
            from flow_request_slas fs
            left join flow_request_work_states fws on fws.routing_id = fs.routing_id
            left join flow_request_sla_events fse on fse.sla_id = fs.id
            where fs.routing_id = %(routing_id)s
            group by fs.id, fws.operational_status, fws.first_response_at_utc
            """,
            {"routing_id": routing_id},
        )
