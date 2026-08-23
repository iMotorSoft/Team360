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

from .mail_query import DEFAULT_MAIL_CUTOFF_EPOCH

_SECTOR_COLUMNS = "sector_id, display_name, active, closure_approval_level::int"
_LEVEL_COLUMNS = (
    "id::text, sector_id, level::int, channel, destination, active, "
    "first_response_sla_seconds"
)


# Default operational settings (used before migration 023/024 is applied).
_DEFAULT_OPERATIONAL_SETTINGS: dict = {
    "automation_enabled": False,
    "scheduler_interval_seconds": 15,
    "mail_intake_enabled": True,
    "mail_batch_limit": 500,
    "mail_after_cutoff": True,
    "mail_cutoff_epoch": DEFAULT_MAIL_CUTOFF_EPOCH,
}


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

    async def update_first_response_sla(
        self,
        conn: AsyncConnection,
        *,
        sector_id: str,
        level: int,
        first_response_sla_seconds: int | None,
    ) -> int | None:
        return await execute(
            conn,
            """
            update flow_sector_levels
            set first_response_sla_seconds = %(first_response_sla_seconds)s,
                updated_at_utc = now()
            where sector_id = %(sector_id)s
              and level = %(level)s
            """,
            {
                "sector_id": sector_id,
                "level": level,
                "first_response_sla_seconds": first_response_sla_seconds,
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

    # --- Operational settings ---

    async def get_operational_settings(self, conn: AsyncConnection) -> dict:
        try:
            return await fetch_one(
                conn,
                """
                select
                    automation_enabled,
                    scheduler_interval_seconds,
                    mail_intake_enabled,
                    mail_batch_limit,
                    mail_after_cutoff,
                    mail_cutoff_epoch
                from flow_operational_settings
                where id = 1
                """,
            )
        except Exception:
            # Migration 023/024 not yet applied; return defaults.
            return dict(_DEFAULT_OPERATIONAL_SETTINGS)

    async def update_operational_settings(
        self,
        conn: AsyncConnection,
        *,
        automation_enabled: bool | None = None,
        scheduler_interval_seconds: int | None = None,
        mail_intake_enabled: bool | None = None,
        mail_batch_limit: int | None = None,
        mail_after_cutoff: bool | None = None,
        mail_cutoff_epoch: int | None = None,
    ) -> dict:
        sets = []
        params: dict = {}
        if automation_enabled is not None:
            sets.append("automation_enabled = %(automation_enabled)s")
            params["automation_enabled"] = automation_enabled
        if scheduler_interval_seconds is not None:
            sets.append(
                "scheduler_interval_seconds = %(scheduler_interval_seconds)s"
            )
            params["scheduler_interval_seconds"] = scheduler_interval_seconds
        if mail_intake_enabled is not None:
            sets.append("mail_intake_enabled = %(mail_intake_enabled)s")
            params["mail_intake_enabled"] = mail_intake_enabled
        if mail_batch_limit is not None:
            sets.append("mail_batch_limit = %(mail_batch_limit)s")
            params["mail_batch_limit"] = mail_batch_limit
        if mail_after_cutoff is not None:
            sets.append("mail_after_cutoff = %(mail_after_cutoff)s")
            params["mail_after_cutoff"] = mail_after_cutoff
        if mail_cutoff_epoch is not None:
            sets.append("mail_cutoff_epoch = %(mail_cutoff_epoch)s")
            params["mail_cutoff_epoch"] = mail_cutoff_epoch
        if not sets:
            return await self.get_operational_settings(conn)
        sets.append("updated_at_utc = now()")
        await execute(
            conn,
            f"update flow_operational_settings set {', '.join(sets)} where id = 1",
            params,
        )
        return await self.get_operational_settings(conn)
