import asyncio

import pytest

from modules.console.errors import UserNotFoundError, WorkspaceNotFoundError
from modules.console.repositories import PermissionConsoleRepository
from modules.console.service import ConsoleBootstrapService


def _summary(**overrides):
    summary = {
        "pending": 0,
        "waiting_approval": 0,
        "failed": 0,
        "completed_today": 0,
        "blocked_by_policy": 0,
    }
    summary.update(overrides)
    return summary


class FakeWorkspaceRepository:
    def __init__(self, user_type="client", workspace=True, user=True):
        self.user_type = user_type
        self.workspace = workspace
        self.user = user

    async def get_workspace(self, conn, workspace_id):
        if not self.workspace:
            return None
        return {
            "workspace_id": workspace_id,
            "workspace_code": "ws-client",
            "display_name": "Client Workspace",
            "workspace_type": "client",
            "status": "active",
        }

    async def get_current_user_context(self, conn, workspace_id, user_id):
        if not self.user:
            return None
        return {
            "user_id": user_id,
            "display_name": "Console User",
            "email": "user@example.com",
            "user_type": self.user_type,
            "area_id": None,
            "roles": [],
            "permission_profiles": [],
        }

    async def list_workspace_areas(self, conn, workspace_id):
        return [{"area_id": "area-1", "area_code": "ops", "display_name": "Ops"}]


class FakePermissionRepository(PermissionConsoleRepository):
    def __init__(self, permissions):
        self.permissions = permissions

    async def list_effective_permissions(self, conn, workspace_id, user_id):
        return list(self.permissions)


class FakePackageRepository:
    def __init__(self, features=None):
        self.features = features or []

    async def get_package_entitlements(self, conn, workspace_id):
        return {
            "plan_code": "operational",
            "plan_display_name": "Operational",
            "features": list(self.features),
        }

    async def list_visible_packages(self, conn, workspace_id, user_id, permissions):
        if "package.view" not in permissions:
            return []
        return [
            {
                "service_id": "package-1",
                "package_id": "package-1",
                "package_code": "commercial_continuity",
                "package_name": "Commercial Continuity",
                "display_name": "Commercial Continuity",
                "status": "active",
                "health": "healthy",
                "plan_code": "operational",
                "category": "sales_operations",
                "summary": "Internal-safe summary",
                "client_summary": "Client summary",
                "has_knowledge": True,
                "has_workers_visible": "worker.view" in permissions,
                "visibility_level": "client",
            }
        ]


class FakeTaskRepository:
    async def get_workspace_task_summary(self, conn, workspace_id, user_id, permissions):
        return _summary(pending=2) if "task.view" in permissions else _summary()

    async def get_package_task_summary(self, conn, package_id, user_id, permissions):
        return _summary(pending=1) if "task.view" in permissions else _summary()

    async def list_workspace_alerts(self, conn, workspace_id, user_id, permissions):
        return []


def _service(user_type="client", permissions=None, features=None, workspace=True, user=True):
    return ConsoleBootstrapService(
        workspace_repository=FakeWorkspaceRepository(user_type, workspace, user),
        permission_repository=FakePermissionRepository(permissions or []),
        package_repository=FakePackageRepository(features),
        task_repository=FakeTaskRepository(),
    )


def _build(service):
    return asyncio.run(service.build_bootstrap(None, "workspace-1", "user-1"))


def test_build_bootstrap_maps_services_and_default_task_summary():
    bootstrap = _build(
        _service(
            permissions=["package.view"],
            features=["events.basic"],
        )
    )

    assert bootstrap.services[0]["package_id"] == "package-1"
    assert bootstrap.services[0]["client_summary"] == "Client summary"
    assert bootstrap.services[0]["task_summary"] == _summary()
    assert bootstrap.tasks_summary == _summary()


def test_debug_is_omitted_for_client_context():
    bootstrap = _build(_service(permissions=["package.view"]))
    assert bootstrap.debug is None


def test_debug_is_included_for_internal_context():
    bootstrap = _build(_service(user_type="internal", permissions=["audit.view"]))
    assert bootstrap.debug is not None
    assert bootstrap.debug["source"] == "backend"


def test_workers_are_hidden_without_worker_permission():
    bootstrap = _build(
        _service(
            permissions=["package.view", "task.view"],
            features=["workers.internal"],
        )
    )
    assert bootstrap.services[0]["has_workers_visible"] is False
    assert "can_view_workers" not in bootstrap.capabilities


def test_capabilities_are_derived_from_permissions_and_entitlements():
    bootstrap = _build(
        _service(
            user_type="internal",
            permissions=[
                "dashboard.view",
                "package.view",
                "task.view",
                "worker.view",
                "knowledge.view",
                "user.manage",
            ],
            features=[
                "dashboard.basic",
                "events.basic",
                "rag.simple",
                "workers.internal",
            ],
        )
    )
    assert {
        "can_view_dashboard",
        "can_view_services",
        "can_view_tasks",
        "can_view_workers",
        "can_view_runs",
        "can_view_reports",
        "can_view_alerts",
        "can_manage_users",
        "can_view_knowledge",
    } <= set(bootstrap.capabilities)


def test_missing_workspace_raises_domain_error():
    with pytest.raises(WorkspaceNotFoundError):
        _build(_service(workspace=False))


def test_missing_user_raises_domain_error():
    with pytest.raises(UserNotFoundError):
        _build(_service(user=False))
