"""PostgreSQL repository for deterministic Flow request routing."""

from __future__ import annotations

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_one

from .domain.routing import (
    INITIAL_N1_ROUTING_KEY,
    INITIAL_ROUTING_LEVEL,
    ConfirmedFlowRequest,
    FlowSector,
    FlowSectorLevel,
    RoutingAssignment,
    RoutingStatus,
)


def _assignment(row: dict | None) -> RoutingAssignment | None:
    if row is None:
        return None
    return RoutingAssignment(
        id=row["id"],
        request_id=row["request_id"],
        routing_key=row["routing_key"],
        sector_id=row["sector_id"],
        level=int(row["level"]),
        channel=row["channel"],
        destination=row["destination"],
        status=RoutingStatus(row["status"]),
        outbound_rfc_message_id=row["outbound_rfc_message_id"],
        outbound_external_message_id=row["outbound_external_message_id"],
        attempt_count=int(row["attempt_count"]),
        delivery_uncertain=bool(row["delivery_uncertain"]),
        last_error_code=row["last_error_code"],
    )


_ASSIGNMENT_COLUMNS = """
    id::text, request_id::text, routing_key, sector_id, level, channel,
    destination, status, outbound_rfc_message_id,
    outbound_external_message_id, attempt_count, delivery_uncertain,
    last_error_code
"""


class FlowRoutingPostgresRepository:
    """Routing SQL with caller-owned connections and transactions."""

    async def get_request(
        self, conn: AsyncConnection, request_id: str
    ) -> ConfirmedFlowRequest | None:
        row = await fetch_one(
            conn,
            """
            select fr.id::text, fr.conversation_id::text, fr.status,
                   fr.description, fr.tentative_category, fr.location_text,
                   fc.channel as origin_channel, fc.citizen_address,
                   fc.external_thread_id
            from flow_requests fr
            join flow_conversations fc on fc.id = fr.conversation_id
            where fr.id = %(request_id)s
            """,
            {"request_id": request_id},
        )
        if row is None:
            return None
        return ConfirmedFlowRequest(**row)

    async def get_sector(
        self, conn: AsyncConnection, sector_id: str
    ) -> FlowSector | None:
        row = await fetch_one(
            conn,
            """
            select sector_id, display_name, active
            from flow_sectors
            where sector_id = %(sector_id)s
            """,
            {"sector_id": sector_id},
        )
        return FlowSector(**row) if row else None

    async def get_sector_level(
        self, conn: AsyncConnection, sector_id: str, level: int
    ) -> FlowSectorLevel | None:
        row = await fetch_one(
            conn,
            """
            select id::text, sector_id, level, channel, destination, active
            from flow_sector_levels
            where sector_id = %(sector_id)s and level = %(level)s
            """,
            {"sector_id": sector_id, "level": level},
        )
        return FlowSectorLevel(**row) if row else None

    async def get_assignment(
        self, conn: AsyncConnection, request_id: str
    ) -> RoutingAssignment | None:
        row = await fetch_one(
            conn,
            f"""
            select {_ASSIGNMENT_COLUMNS}
            from flow_request_routings
            where request_id = %(request_id)s and routing_key = %(routing_key)s
            for update
            """,
            {"request_id": request_id, "routing_key": INITIAL_N1_ROUTING_KEY},
        )
        return _assignment(row)

    async def create_pending_assignment(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        sector: FlowSector,
        sector_level: FlowSectorLevel,
        outbound_rfc_message_id: str,
    ) -> RoutingAssignment:
        row = await fetch_one(
            conn,
            f"""
            insert into flow_request_routings (
                request_id, routing_key, sector_id, sector_level_id, level,
                channel, destination, status, outbound_rfc_message_id
            ) values (
                %(request_id)s, %(routing_key)s, %(sector_id)s,
                %(sector_level_id)s, %(level)s, %(channel)s, %(destination)s,
                'ROUTING_PENDING', %(outbound_rfc_message_id)s
            )
            on conflict (request_id, routing_key) do nothing
            returning {_ASSIGNMENT_COLUMNS}
            """,
            {
                "request_id": request_id,
                "routing_key": INITIAL_N1_ROUTING_KEY,
                "sector_id": sector.sector_id,
                "sector_level_id": sector_level.id,
                "level": sector_level.level,
                "channel": sector_level.channel,
                "destination": sector_level.destination,
                "outbound_rfc_message_id": outbound_rfc_message_id,
            },
        )
        created = _assignment(row)
        if created is not None:
            return created
        existing = await self.get_assignment(conn, request_id)
        if existing is None:
            raise RuntimeError("Flow routing assignment conflict returned no row.")
        return existing

    async def create_unresolved_assignment(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        sector_id: str | None,
        error_code: str,
    ) -> RoutingAssignment:
        row = await fetch_one(
            conn,
            f"""
            insert into flow_request_routings (
                request_id, routing_key, sector_id, level, status,
                last_error_code, last_error_detail
            ) values (
                %(request_id)s, %(routing_key)s, %(sector_id)s,
                %(level)s, 'ROUTING_UNRESOLVED', %(error_code)s,
                'Routing could not be resolved from the active Flow catalog.'
            )
            on conflict (request_id, routing_key) do nothing
            returning {_ASSIGNMENT_COLUMNS}
            """,
            {
                "request_id": request_id,
                "routing_key": INITIAL_N1_ROUTING_KEY,
                "sector_id": sector_id,
                "level": INITIAL_ROUTING_LEVEL,
                "error_code": error_code,
            },
        )
        created = _assignment(row)
        if created is not None:
            return created
        existing = await self.get_assignment(conn, request_id)
        if existing is None:
            raise RuntimeError("Flow unresolved routing conflict returned no row.")
        return existing

    async def mark_attempt(
        self, conn: AsyncConnection, assignment_id: str
    ) -> RoutingAssignment:
        row = await fetch_one(
            conn,
            f"""
            update flow_request_routings
            set status = 'ROUTING_PENDING',
                attempt_count = attempt_count + 1,
                last_error_code = null,
                last_error_detail = null,
                updated_at_utc = now()
            where id = %(assignment_id)s
            returning {_ASSIGNMENT_COLUMNS}
            """,
            {"assignment_id": assignment_id},
        )
        assignment = _assignment(row)
        if assignment is None:
            raise RuntimeError("Flow routing attempt update returned no row.")
        return assignment

    async def mark_assigned(
        self,
        conn: AsyncConnection,
        *,
        assignment_id: str,
        external_message_id: str,
    ) -> RoutingAssignment:
        row = await fetch_one(
            conn,
            f"""
            update flow_request_routings
            set status = 'ASSIGNED',
                outbound_external_message_id = %(external_message_id)s,
                delivery_uncertain = false,
                last_error_code = null,
                last_error_detail = null,
                assigned_at_utc = now(),
                updated_at_utc = now()
            where id = %(assignment_id)s
            returning {_ASSIGNMENT_COLUMNS}
            """,
            {
                "assignment_id": assignment_id,
                "external_message_id": external_message_id,
            },
        )
        assignment = _assignment(row)
        if assignment is None:
            raise RuntimeError("Flow routing assigned update returned no row.")
        return assignment

    async def mark_failed(
        self,
        conn: AsyncConnection,
        *,
        assignment_id: str,
        error_code: str,
        delivery_uncertain: bool,
    ) -> RoutingAssignment:
        row = await fetch_one(
            conn,
            f"""
            update flow_request_routings
            set status = 'ROUTING_FAILED',
                delivery_uncertain = %(delivery_uncertain)s,
                last_error_code = %(error_code)s,
                last_error_detail = 'Gmail delivery failed; retry requires reconciliation.',
                updated_at_utc = now()
            where id = %(assignment_id)s
            returning {_ASSIGNMENT_COLUMNS}
            """,
            {
                "assignment_id": assignment_id,
                "delivery_uncertain": delivery_uncertain,
                "error_code": error_code,
            },
        )
        assignment = _assignment(row)
        if assignment is None:
            raise RuntimeError("Flow routing failed update returned no row.")
        return assignment

    async def routing_evidence(
        self, conn: AsyncConnection, request_id: str
    ) -> dict | None:
        return await fetch_one(
            conn,
            """
            select frr.id::text as routing_id, frr.request_id::text,
                   frr.routing_key, frr.sector_id, frr.level, frr.channel,
                   frr.destination, frr.status,
                   frr.outbound_rfc_message_id,
                   frr.outbound_external_message_id, frr.attempt_count,
                   frr.delivery_uncertain, frr.last_error_code,
                   frr.routed_at_utc, frr.assigned_at_utc
            from flow_request_routings frr
            where frr.request_id = %(request_id)s
              and frr.routing_key = %(routing_key)s
            """,
            {"request_id": request_id, "routing_key": INITIAL_N1_ROUTING_KEY},
        )
