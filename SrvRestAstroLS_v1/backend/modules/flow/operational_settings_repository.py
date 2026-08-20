"""PostgreSQL repository for Flow operational settings.

Single-row configuration table ``flow_operational_settings`` and scheduler
state ``flow_scheduler_state``. These are MODULE_LOCAL to Flow and do not
affect Diagnosis or other Team360 products.
"""

from __future__ import annotations

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_one


class FlowOperationalSettingsRepository:
    """Reads and writes the single-row operational settings."""

    async def get_settings(self, conn: AsyncConnection) -> dict:
        return await fetch_one(
            conn,
            """
            select
                automation_enabled,
                scheduler_interval_seconds,
                mail_intake_enabled,
                mail_batch_limit,
                mail_after_cutoff
            from flow_operational_settings
            where id = 1
            """,
        )

    async def update_settings(
        self,
        conn: AsyncConnection,
        *,
        automation_enabled: bool | None = None,
        scheduler_interval_seconds: int | None = None,
        mail_intake_enabled: bool | None = None,
        mail_batch_limit: int | None = None,
        mail_after_cutoff: bool | None = None,
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
        if not sets:
            return await self.get_settings(conn)
        sets.append("updated_at_utc = now()")
        await execute(
            conn,
            f"update flow_operational_settings set {', '.join(sets)} where id = 1",
            params,
        )
        return await self.get_settings(conn)


class FlowSchedulerStateRepository:
    """Reads and writes the single-row scheduler execution state."""

    async def get_state(self, conn: AsyncConnection) -> dict:
        return await fetch_one(
            conn,
            """
            select
                last_started_at_utc,
                last_finished_at_utc,
                last_result,
                last_error_class,
                processed_count,
                cycle_count
            from flow_scheduler_state
            where id = 1
            """,
        )

    async def record_cycle_start(self, conn: AsyncConnection) -> None:
        await execute(
            conn,
            """
            update flow_scheduler_state
            set last_started_at_utc = now(),
                last_finished_at_utc = null,
                last_result = null,
                last_error_class = null,
                updated_at_utc = now()
            where id = 1
            """,
        )

    async def record_cycle_finish(
        self,
        conn: AsyncConnection,
        *,
        result: str,
        error_class: str | None,
        processed: int,
    ) -> None:
        await execute(
            conn,
            """
            update flow_scheduler_state
            set last_finished_at_utc = now(),
                last_result = %(result)s,
                last_error_class = %(error_class)s,
                processed_count = processed_count + %(processed)s,
                cycle_count = cycle_count + 1,
                updated_at_utc = now()
            where id = 1
            """,
            {
                "result": result,
                "error_class": error_class,
                "processed": processed,
            },
        )
