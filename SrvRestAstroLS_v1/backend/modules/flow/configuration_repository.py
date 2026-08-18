"""PostgreSQL repository for Flow sector routing configuration.

Administers the policy that Flow already consumes at runtime:

- ``flow_sectors`` (display_name, active, closure_approval_level)
- ``flow_sector_levels`` (level, channel, destination, active,
  first_response_sla_seconds)

The destination captured by routings and closure approvals is snapshotted at
creation time, so updates here affect only future workflow events.
"""

from __future__ import annotations

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_all, fetch_one

_SECTOR_COLUMNS = "sector_id, display_name, active, closure_approval_level::int"
_LEVEL_COLUMNS = (
    "id::text, sector_id, level::int, channel, destination, active, "
    "first_response_sla_seconds"
)


class FlowConfigurationPostgresRepository:
    """Configuration SQL with caller-owned connections and transactions."""

    async def list_sectors(self, conn: AsyncConnection) -> list[dict]:
        return await fetch_all(
            conn,
            f"""
            select {_SECTOR_COLUMNS}
            from flow_sectors
            order by sector_id
            """,
        )

    async def list_levels(self, conn: AsyncConnection) -> list[dict]:
        return await fetch_all(
            conn,
            f"""
            select {_LEVEL_COLUMNS}
            from flow_sector_levels
            order by sector_id, level
            """,
        )

    async def get_sector(
        self, conn: AsyncConnection, sector_id: str
    ) -> dict | None:
        return await fetch_one(
            conn,
            f"""
            select {_SECTOR_COLUMNS}
            from flow_sectors
            where sector_id = %(sector_id)s
            """,
            {"sector_id": sector_id},
        )

    async def get_levels(
        self, conn: AsyncConnection, sector_id: str
    ) -> list[dict]:
        return await fetch_all(
            conn,
            f"""
            select {_LEVEL_COLUMNS}
            from flow_sector_levels
            where sector_id = %(sector_id)s
            order by level
            """,
            {"sector_id": sector_id},
        )

    async def update_destination(
        self,
        conn: AsyncConnection,
        *,
        sector_id: str,
        level: int,
        destination: str,
    ) -> int | None:
        return await execute(
            conn,
            """
            update flow_sector_levels
            set destination = %(destination)s,
                updated_at_utc = now()
            where sector_id = %(sector_id)s
              and level = %(level)s
            """,
            {
                "sector_id": sector_id,
                "level": level,
                "destination": destination,
            },
        )

    async def update_closure_approval_level(
        self,
        conn: AsyncConnection,
        *,
        sector_id: str,
        closure_approval_level: int | None,
    ) -> int | None:
        return await execute(
            conn,
            """
            update flow_sectors
            set closure_approval_level = %(closure_approval_level)s,
                updated_at_utc = now()
            where sector_id = %(sector_id)s
            """,
            {
                "sector_id": sector_id,
                "closure_approval_level": closure_approval_level,
            },
        )
