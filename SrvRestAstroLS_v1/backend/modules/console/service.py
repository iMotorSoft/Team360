from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from modules.console.errors import UserNotFoundError, WorkspaceNotFoundError
from modules.console.repositories import (
    PackageConsoleRepository,
    PermissionConsoleRepository,
    TaskConsoleRepository,
    WorkspaceConsoleRepository,
)
from modules.console.types import (
    ConsoleBootstrap,
    CurrentUserDTO,
    EntitlementsDTO,
    NavGroupDTO,
    OrgContextDTO,
    ServiceDTO,
    WorkspaceDTO,
)

_INTERNAL_FEATURES = {"workers.internal", "workers.external"}
_VALID_USER_TYPES = {"internal", "partner", "client"}
_VALID_WORKSPACE_TYPES = {"team360", "partner", "client", "internal"}
_VALID_VISIBILITY_LEVELS = {"client", "partner", "internal"}


class ConsoleBootstrapService:
    def __init__(
        self,
        workspace_repository: WorkspaceConsoleRepository | None = None,
        permission_repository: PermissionConsoleRepository | None = None,
        package_repository: PackageConsoleRepository | None = None,
        task_repository: TaskConsoleRepository | None = None,
    ) -> None:
        self.workspace_repository = workspace_repository or WorkspaceConsoleRepository()
        self.permission_repository = permission_repository or PermissionConsoleRepository()
        self.package_repository = package_repository or PackageConsoleRepository()
        self.task_repository = task_repository or TaskConsoleRepository()

    async def build_bootstrap(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        user_id: str,
        profile: str | None = None,
    ) -> ConsoleBootstrap:
        # profile is reserved for a future authenticated HTTP boundary. It never
        # grants permissions or internal visibility by itself.
        _ = profile

        workspace_row = await self.workspace_repository.get_workspace(conn, workspace_id)
        if workspace_row is None:
            raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")

        user_row = await self.workspace_repository.get_current_user_context(
            conn,
            workspace_id,
            user_id,
        )
        if user_row is None:
            raise UserNotFoundError(
                f"User not found in requested workspace: {user_id}"
            )

        workspace = self._workspace_dto(workspace_row)
        current_user = self._current_user_dto(user_row)
        permissions = await self.permission_repository.list_effective_permissions(
            conn,
            workspace_id,
            user_id,
        )
        entitlements = await self.package_repository.get_package_entitlements(
            conn,
            workspace_id,
        )
        capability_flags = self.permission_repository.derive_capabilities(permissions)
        self._apply_entitlements(capability_flags, entitlements["features"])
        capabilities = sorted(
            capability for capability, enabled in capability_flags.items() if enabled
        )

        package_rows = await self.package_repository.list_visible_packages(
            conn,
            workspace_id,
            user_id,
            permissions,
        )
        services = [
            await self._service_dto(conn, package_row, user_id, permissions)
            for package_row in package_rows
        ]
        tasks_summary = await self.task_repository.get_workspace_task_summary(
            conn,
            workspace_id,
            user_id,
            permissions,
        )
        alerts = await self.task_repository.list_workspace_alerts(
            conn,
            workspace_id,
            user_id,
            permissions,
        )
        areas = await self.workspace_repository.list_workspace_areas(conn, workspace_id)

        debug = None
        if current_user["user_type"] == "internal" or "audit.view" in permissions:
            debug = {
                "source": "backend",
                "permissions_evaluated": len(permissions),
                "hidden_items_count": self._hidden_items_count(capability_flags, services),
                "feature_flags": {
                    "agui_enabled": False,
                    "rtl_preview": True,
                    "organization_switcher": False,
                    "workspace_switcher": False,
                },
            }

        return ConsoleBootstrap(
            workspace=workspace,
            current_user=current_user,
            effective_permissions=permissions,
            capabilities=capabilities,
            entitlements=entitlements,
            navigation=self._build_navigation(workspace_id, capability_flags),
            services=services,
            tasks_summary=tasks_summary,
            alerts=alerts,
            workspace_context={
                "active_area": current_user["area_id"],
                "available_areas": areas,
                "selected_package": None,
            },
            organization_context=self._provisional_organization_context(workspace),
            debug=debug,
        )

    async def _service_dto(
        self,
        conn: AsyncConnection,
        package: dict[str, Any],
        user_id: str,
        permissions: list[str],
    ) -> ServiceDTO:
        task_summary = await self.task_repository.get_package_task_summary(
            conn,
            str(package["package_id"]),
            user_id,
            permissions,
        )
        visibility_level = str(package["visibility_level"])
        if visibility_level not in _VALID_VISIBILITY_LEVELS:
            visibility_level = "client"
        return {
            "service_id": str(package["service_id"]),
            "package_id": str(package["package_id"]),
            "package_code": str(package["package_code"]),
            "package_name": str(package["package_name"]),
            "display_name": str(package["display_name"]),
            "status": package["status"],
            "health": package["health"],
            "plan_code": str(package["plan_code"]),
            "category": str(package["category"]),
            "summary": str(package["summary"]),
            "client_summary": str(package["client_summary"]),
            "task_summary": task_summary,
            "has_knowledge": bool(package["has_knowledge"]),
            "has_workers_visible": bool(package["has_workers_visible"]),
            "visibility_level": visibility_level,
        }

    @staticmethod
    def _workspace_dto(workspace: dict[str, Any]) -> WorkspaceDTO:
        workspace_type = str(workspace["workspace_type"])
        if workspace_type not in _VALID_WORKSPACE_TYPES:
            workspace_type = "client"
        return {
            "workspace_id": str(workspace["workspace_id"]),
            "workspace_code": str(workspace["workspace_code"]),
            "display_name": str(workspace["display_name"]),
            "workspace_type": workspace_type,
            "status": workspace["status"],
        }

    @staticmethod
    def _current_user_dto(user: dict[str, Any]) -> CurrentUserDTO:
        user_type = str(user["user_type"])
        if user_type not in _VALID_USER_TYPES:
            user_type = "client"
        return {
            "user_id": str(user["user_id"]),
            "display_name": str(user["display_name"]),
            "email": str(user["email"]),
            "user_type": user_type,
            "area_id": user["area_id"],
            "roles": user["roles"],
            "permission_profiles": user["permission_profiles"],
        }

    @staticmethod
    def _apply_entitlements(
        capabilities: dict[str, bool],
        features: list[str],
    ) -> None:
        enabled_features = set(features)
        capabilities["can_view_dashboard"] = (
            capabilities["can_view_dashboard"] and "dashboard.basic" in enabled_features
        )
        capabilities["can_view_workers"] = (
            capabilities["can_view_workers"] and bool(_INTERNAL_FEATURES & enabled_features)
        )
        capabilities["can_view_runs"] = (
            capabilities["can_view_runs"] and capabilities["can_view_workers"]
        )
        capabilities["can_view_knowledge"] = (
            capabilities["can_view_knowledge"] and "rag.simple" in enabled_features
        )
        capabilities["can_view_reports"] = "dashboard.basic" in enabled_features
        capabilities["can_view_alerts"] = "events.basic" in enabled_features
        # The current schema has a single workspace_id on core_users, not memberships.
        capabilities["can_switch_workspace"] = False

    @staticmethod
    def _build_navigation(
        workspace_id: str,
        capabilities: dict[str, bool],
    ) -> list[NavGroupDTO]:
        groups: list[NavGroupDTO] = []
        platform_items = []
        operation_items = []
        technical_items = []

        if capabilities["can_view_dashboard"]:
            platform_items.append(
                {"id": "dashboard", "label": "Dashboard", "route": f"/w/{workspace_id}", "icon": "home"}
            )
        if capabilities["can_view_services"]:
            platform_items.append(
                {"id": "services", "label": "Servicios", "route": f"/w/{workspace_id}/services", "icon": "package"}
            )
        if capabilities["can_view_tasks"]:
            operation_items.append(
                {"id": "tasks", "label": "Tareas", "route": f"/w/{workspace_id}/tasks", "icon": "checklist"}
            )
        if capabilities["can_view_alerts"]:
            operation_items.append(
                {"id": "alerts", "label": "Alertas", "route": f"/w/{workspace_id}/alerts", "icon": "bell"}
            )
        if capabilities["can_view_reports"]:
            operation_items.append(
                {"id": "reports", "label": "Reportes", "route": f"/w/{workspace_id}/reports", "icon": "chart"}
            )
        if capabilities["can_view_workers"]:
            technical_items.append(
                {"id": "workers", "label": "Workers", "route": f"/w/{workspace_id}/workers", "icon": "cpu"}
            )
        if capabilities["can_view_runs"]:
            technical_items.append(
                {"id": "runs", "label": "Ejecuciones", "route": f"/w/{workspace_id}/runs", "icon": "activity"}
            )

        if platform_items:
            groups.append({"group": "Plataforma", "items": platform_items})
        if operation_items:
            groups.append({"group": "Operacion", "items": operation_items})
        if technical_items:
            groups.append(
                {
                    "group": "Tecnico",
                    "visibility_level": "internal",
                    "items": technical_items,
                }
            )
        return groups

    @staticmethod
    def _provisional_organization_context(workspace: WorkspaceDTO) -> OrgContextDTO:
        # The organization tables are intentionally deferred to a future migration.
        return {
            "organization_id": workspace["workspace_id"],
            "organization_code": workspace["workspace_code"],
            "display_name": workspace["display_name"],
            "organization_type": workspace["workspace_type"],
            "parent_organization_id": None,
            "status": workspace["status"],
            "access_mode": "own",
            "delegated_by_organization_id": None,
        }

    @staticmethod
    def _hidden_items_count(
        capabilities: dict[str, bool],
        services: list[ServiceDTO],
    ) -> int:
        hidden_technical_items = int(not capabilities["can_view_workers"]) + int(
            not capabilities["can_view_runs"]
        )
        hidden_worker_flags = sum(
            not service["has_workers_visible"] for service in services
        )
        return hidden_technical_items + hidden_worker_flags
