from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from modules.console.types import TaskSummaryDTO

Params = Mapping[str, Any]


async def _fetch_one(
    conn: AsyncConnection,
    sql: str,
    params: Params,
) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(sql, params)
        row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def _fetch_all(
    conn: AsyncConnection,
    sql: str,
    params: Params,
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(sql, params)
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def _task_summary(row: Mapping[str, Any] | None = None) -> TaskSummaryDTO:
    row = row or {}
    return {
        "pending": int(row.get("pending", 0)),
        "waiting_approval": int(row.get("waiting_approval", 0)),
        "failed": int(row.get("failed", 0)),
        "completed_today": int(row.get("completed_today", 0)),
        "blocked_by_policy": int(row.get("blocked_by_policy", 0)),
    }


class WorkspaceConsoleRepository:
    GET_WORKSPACE_SQL = """
        SELECT
            id::text AS workspace_id,
            slug AS workspace_code,
            display_name,
            COALESCE(NULLIF(metadata_jsonb ->> 'workspace_type', ''), 'client')
                AS workspace_type,
            status
        FROM core_workspaces
        WHERE id = %(workspace_id)s::uuid
    """

    GET_CURRENT_USER_SQL = """
        SELECT
            id::text AS user_id,
            COALESCE(NULLIF(display_name, ''), NULLIF(email, ''), 'Usuario')
                AS display_name,
            COALESCE(email, '') AS email,
            COALESCE(NULLIF(metadata_jsonb ->> 'user_type', ''), role, 'client')
                AS user_type
        FROM core_users
        WHERE id = %(user_id)s::uuid
          AND workspace_id = %(workspace_id)s::uuid
          AND status IN ('active', 'testing')
    """

    LIST_USER_ROLES_SQL = """
        SELECT
            role.id::text AS role_id,
            role.role_code,
            role.display_name
        FROM core_user_roles user_role
        JOIN core_roles role ON role.id = user_role.role_id
        WHERE user_role.user_id = %(user_id)s::uuid
          AND (role.workspace_id IS NULL OR role.workspace_id = %(workspace_id)s::uuid)
          AND role.status IN ('active', 'testing')
        ORDER BY role.role_code
    """

    LIST_USER_PROFILES_SQL = """
        SELECT DISTINCT
            profile.id::text AS profile_id,
            profile.profile_code,
            profile.display_name,
            user_profile.area_id::text AS area_id
        FROM core_user_profiles user_profile
        JOIN core_permission_profiles profile ON profile.id = user_profile.profile_id
        WHERE user_profile.user_id = %(user_id)s::uuid
          AND (
              profile.workspace_id IS NULL
              OR profile.workspace_id = %(workspace_id)s::uuid
          )
          AND profile.status IN ('active', 'testing')
        ORDER BY profile.profile_code, area_id
    """

    LIST_WORKSPACE_AREAS_SQL = """
        SELECT
            id::text AS area_id,
            area_code,
            display_name
        FROM core_workspace_areas
        WHERE workspace_id = %(workspace_id)s::uuid
          AND status IN ('active', 'testing')
        ORDER BY display_name, area_code
    """

    async def get_workspace(
        self,
        conn: AsyncConnection,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        return await _fetch_one(conn, self.GET_WORKSPACE_SQL, {"workspace_id": workspace_id})

    async def get_current_user_context(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        params = {"workspace_id": workspace_id, "user_id": user_id}
        user = await _fetch_one(conn, self.GET_CURRENT_USER_SQL, params)
        if user is None:
            return None

        roles = await _fetch_all(conn, self.LIST_USER_ROLES_SQL, params)
        profiles = await _fetch_all(conn, self.LIST_USER_PROFILES_SQL, params)
        area_id = next(
            (profile["area_id"] for profile in profiles if profile["area_id"] is not None),
            None,
        )
        user["area_id"] = area_id
        user["roles"] = roles
        user["permission_profiles"] = [
            {
                "profile_id": profile["profile_id"],
                "profile_code": profile["profile_code"],
                "display_name": profile["display_name"],
            }
            for profile in profiles
        ]
        return user

    async def list_workspace_areas(
        self,
        conn: AsyncConnection,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        return await _fetch_all(
            conn,
            self.LIST_WORKSPACE_AREAS_SQL,
            {"workspace_id": workspace_id},
        )


class PermissionConsoleRepository:
    LIST_EFFECTIVE_PERMISSIONS_SQL = """
        SELECT DISTINCT permission_code
        FROM (
            SELECT permission.permission_code
            FROM core_users app_user
            JOIN core_user_roles user_role ON user_role.user_id = app_user.id
            JOIN core_roles role ON role.id = user_role.role_id
            JOIN core_role_permissions role_permission
                ON role_permission.role_id = role.id
            JOIN core_permissions permission
                ON permission.id = role_permission.permission_id
            WHERE app_user.id = %(user_id)s::uuid
              AND app_user.workspace_id = %(workspace_id)s::uuid
              AND app_user.status IN ('active', 'testing')
              AND (role.workspace_id IS NULL OR role.workspace_id = %(workspace_id)s::uuid)
              AND role.status IN ('active', 'testing')

            UNION

            SELECT permission.permission_code
            FROM core_users app_user
            JOIN core_user_profiles user_profile ON user_profile.user_id = app_user.id
            JOIN core_permission_profiles profile ON profile.id = user_profile.profile_id
            JOIN core_profile_permissions profile_permission
                ON profile_permission.profile_id = profile.id
            JOIN core_permissions permission
                ON permission.id = profile_permission.permission_id
            WHERE app_user.id = %(user_id)s::uuid
              AND app_user.workspace_id = %(workspace_id)s::uuid
              AND app_user.status IN ('active', 'testing')
              AND (
                  profile.workspace_id IS NULL
                  OR profile.workspace_id = %(workspace_id)s::uuid
              )
              AND profile.status IN ('active', 'testing')
        ) granted_permissions
        ORDER BY permission_code
    """

    LIST_PERMISSION_PROFILES_SQL = WorkspaceConsoleRepository.LIST_USER_PROFILES_SQL

    async def list_effective_permissions(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
    ) -> list[str]:
        rows = await _fetch_all(
            conn,
            self.LIST_EFFECTIVE_PERMISSIONS_SQL,
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        return [str(row["permission_code"]) for row in rows]

    async def list_permission_profiles(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        rows = await _fetch_all(
            conn,
            self.LIST_PERMISSION_PROFILES_SQL,
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        return [
            {
                "profile_id": row["profile_id"],
                "profile_code": row["profile_code"],
                "display_name": row["display_name"],
            }
            for row in rows
        ]

    def derive_capabilities(self, permissions: list[str]) -> dict[str, bool]:
        granted = set(permissions)
        return {
            "can_view_dashboard": "dashboard.view" in granted,
            "can_view_services": "package.view" in granted,
            "can_view_tasks": "task.view" in granted,
            "can_view_workers": "worker.view" in granted,
            "can_view_runs": {"task.view", "worker.view"} <= granted,
            "can_manage_users": "user.manage" in granted,
            "can_view_knowledge": "knowledge.view" in granted,
        }


class PackageConsoleRepository:
    LIST_VISIBLE_PACKAGES_SQL = """
        SELECT
            package.id::text AS service_id,
            package.id::text AS package_id,
            package.package_code,
            package.package_name,
            package.package_name AS display_name,
            package.status,
            package.plan_code,
            'automation' AS category,
            package.package_name AS summary,
            package.package_name AS client_summary,
            'client' AS visibility_level,
            EXISTS (
                SELECT 1
                FROM knowledge_scope_bindings binding
                JOIN knowledge_scopes scope ON scope.id = binding.knowledge_scope_id
                WHERE binding.binding_type = 'automation_package'
                  AND binding.bound_entity_id = package.id
                  AND scope.status IN ('active', 'testing')
            ) AS has_knowledge,
            EXISTS (
                SELECT 1
                FROM package_workers package_worker
                WHERE package_worker.automation_package_id = package.id
                  AND package_worker.status IN ('active', 'testing', 'paused', 'error')
            ) AS has_workers,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM package_workers package_worker
                    WHERE package_worker.automation_package_id = package.id
                      AND package_worker.status = 'error'
                ) THEN 'critical'
                WHEN EXISTS (
                    SELECT 1
                    FROM task_runs task_run
                    WHERE task_run.automation_package_id = package.id
                      AND task_run.status = 'failed'
                      AND task_run.updated_at_utc >= now() - interval '24 hours'
                ) THEN 'warning'
                WHEN package.status = 'testing' THEN 'pending'
                ELSE 'healthy'
            END AS health
        FROM automation_packages package
        WHERE package.workspace_id = %(workspace_id)s::uuid
          AND package.status IN ('active', 'testing', 'paused')
          AND EXISTS (
              SELECT 1
              FROM core_users app_user
              WHERE app_user.id = %(user_id)s::uuid
                AND app_user.workspace_id = package.workspace_id
                AND app_user.status IN ('active', 'testing')
          )
        ORDER BY package.package_name, package.package_code
    """

    GET_PACKAGE_ENTITLEMENTS_SQL = """
        SELECT
            plan.plan_code,
            plan.display_name AS plan_display_name,
            COALESCE(
                array_agg(feature.feature_code ORDER BY feature.feature_code)
                    FILTER (WHERE feature.id IS NOT NULL),
                ARRAY[]::text[]
            ) AS features
        FROM workspace_plan_subscriptions subscription
        JOIN package_plans plan ON plan.id = subscription.plan_id
        LEFT JOIN package_plan_features plan_feature ON plan_feature.plan_id = plan.id
        LEFT JOIN package_features feature
            ON feature.id = plan_feature.feature_id
           AND feature.status IN ('active', 'testing')
        WHERE subscription.workspace_id = %(workspace_id)s::uuid
          AND subscription.status = 'active'
          AND plan.status IN ('active', 'testing')
        GROUP BY plan.id, plan.plan_code, plan.display_name, subscription.started_at_utc
        ORDER BY subscription.started_at_utc DESC
        LIMIT 1
    """

    PACKAGE_HAS_KNOWLEDGE_SQL = """
        SELECT EXISTS (
            SELECT 1
            FROM knowledge_scope_bindings binding
            JOIN knowledge_scopes scope ON scope.id = binding.knowledge_scope_id
            WHERE binding.binding_type = 'automation_package'
              AND binding.bound_entity_id = %(package_id)s::uuid
              AND scope.status IN ('active', 'testing')
        ) AS has_knowledge
    """

    PACKAGE_HAS_VISIBLE_WORKERS_SQL = """
        SELECT EXISTS (
            SELECT 1
            FROM package_workers package_worker
            WHERE package_worker.automation_package_id = %(package_id)s::uuid
              AND package_worker.status IN ('active', 'testing', 'paused', 'error')
        ) AS has_workers
    """

    async def list_visible_packages(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
        permissions: list[str],
    ) -> list[dict[str, Any]]:
        if "package.view" not in permissions:
            return []

        rows = await _fetch_all(
            conn,
            self.LIST_VISIBLE_PACKAGES_SQL,
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        can_view_workers = "worker.view" in permissions
        for row in rows:
            row["has_workers_visible"] = bool(row.pop("has_workers")) and can_view_workers
        return rows

    async def get_package_entitlements(
        self,
        conn: AsyncConnection,
        workspace_id: str,
    ) -> dict[str, Any]:
        row = await _fetch_one(
            conn,
            self.GET_PACKAGE_ENTITLEMENTS_SQL,
            {"workspace_id": workspace_id},
        )
        if row is None:
            return {
                "plan_code": "unassigned",
                "plan_display_name": "Sin plan activo",
                "features": [],
            }
        row["features"] = list(row["features"])
        return row

    async def package_has_knowledge(
        self,
        conn: AsyncConnection,
        package_id: str,
    ) -> bool:
        row = await _fetch_one(
            conn,
            self.PACKAGE_HAS_KNOWLEDGE_SQL,
            {"package_id": package_id},
        )
        return bool(row and row["has_knowledge"])

    async def package_has_visible_workers(
        self,
        conn: AsyncConnection,
        package_id: str,
        permissions: list[str],
    ) -> bool:
        if "worker.view" not in permissions:
            return False
        row = await _fetch_one(
            conn,
            self.PACKAGE_HAS_VISIBLE_WORKERS_SQL,
            {"package_id": package_id},
        )
        return bool(row and row["has_workers"])


class TaskConsoleRepository:
    GET_WORKSPACE_TASK_SUMMARY_SQL = """
        SELECT
            count(*) FILTER (WHERE task_run.status = 'pending')::int AS pending,
            count(*) FILTER (WHERE task_run.approval_status = 'pending')::int
                AS waiting_approval,
            count(*) FILTER (WHERE task_run.status = 'failed')::int AS failed,
            count(*) FILTER (
                WHERE task_run.status = 'completed'
                  AND task_run.updated_at_utc >= current_date
            )::int AS completed_today,
            (
                SELECT count(*)::int
                FROM package_workers package_worker
                WHERE package_worker.workspace_id = %(workspace_id)s::uuid
                  AND package_worker.mode = 'blocked'
                  AND package_worker.status <> 'retired'
            ) AS blocked_by_policy
        FROM task_runs task_run
        WHERE task_run.workspace_id = %(workspace_id)s::uuid
          AND EXISTS (
              SELECT 1
              FROM core_users app_user
              WHERE app_user.id = %(user_id)s::uuid
                AND app_user.workspace_id = task_run.workspace_id
                AND app_user.status IN ('active', 'testing')
          )
    """

    GET_PACKAGE_TASK_SUMMARY_SQL = """
        SELECT
            count(*) FILTER (WHERE task_run.status = 'pending')::int AS pending,
            count(*) FILTER (WHERE task_run.approval_status = 'pending')::int
                AS waiting_approval,
            count(*) FILTER (WHERE task_run.status = 'failed')::int AS failed,
            count(*) FILTER (
                WHERE task_run.status = 'completed'
                  AND task_run.updated_at_utc >= current_date
            )::int AS completed_today,
            (
                SELECT count(*)::int
                FROM package_workers package_worker
                WHERE package_worker.automation_package_id = %(package_id)s::uuid
                  AND package_worker.mode = 'blocked'
                  AND package_worker.status <> 'retired'
            ) AS blocked_by_policy
        FROM task_runs task_run
        JOIN automation_packages package ON package.id = task_run.automation_package_id
        WHERE task_run.automation_package_id = %(package_id)s::uuid
          AND EXISTS (
              SELECT 1
              FROM core_users app_user
              WHERE app_user.id = %(user_id)s::uuid
                AND app_user.workspace_id = package.workspace_id
                AND app_user.status IN ('active', 'testing')
          )
    """

    LIST_WORKSPACE_ALERTS_SQL = """
        SELECT
            event.id::text AS alert_id,
            'info' AS severity,
            event.event_name AS message,
            concat_ws(':', event.entity_type, event.entity_id::text) AS target,
            event.occurred_at_utc::text AS created_at_utc,
            'open' AS status
        FROM core_events event
        WHERE event.workspace_id = %(workspace_id)s::uuid
          AND event.event_name LIKE 'console.alert.%%'
          AND EXISTS (
              SELECT 1
              FROM core_users app_user
              WHERE app_user.id = %(user_id)s::uuid
                AND app_user.workspace_id = event.workspace_id
                AND app_user.status IN ('active', 'testing')
          )
        ORDER BY event.occurred_at_utc DESC
        LIMIT 20
    """

    async def get_workspace_task_summary(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
        permissions: list[str],
    ) -> TaskSummaryDTO:
        if "task.view" not in permissions:
            return _task_summary()
        row = await _fetch_one(
            conn,
            self.GET_WORKSPACE_TASK_SUMMARY_SQL,
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        return _task_summary(row)

    async def get_package_task_summary(
        self,
        conn: AsyncConnection,
        package_id: str,
        user_id: str,
        permissions: list[str],
    ) -> TaskSummaryDTO:
        if "task.view" not in permissions:
            return _task_summary()
        row = await _fetch_one(
            conn,
            self.GET_PACKAGE_TASK_SUMMARY_SQL,
            {"package_id": package_id, "user_id": user_id},
        )
        return _task_summary(row)

    async def list_workspace_alerts(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
        permissions: list[str],
    ) -> list[dict[str, Any]]:
        if not {"task.view", "audit.view"} & set(permissions):
            return []
        return await _fetch_all(
            conn,
            self.LIST_WORKSPACE_ALERTS_SQL,
            {"workspace_id": workspace_id, "user_id": user_id},
        )
