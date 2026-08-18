"""Authorization guard for Flow configuration management.

Separates AUTHENTICATION (PASETO console token) from AUTHORIZATION (persistent
capabilities ``flow.configuration.read`` and ``flow.configuration.write``
resolved from the existing RBAC). Fail closed: without the explicit
capability every request is denied before any data access, and the write
capability never implies the read-only executive permission scope.

``flow.executive.read`` does NOT grant configuration access.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from modules.console.repositories import PermissionConsoleRepository
from modules.flow.executive_auth import FlowExecutiveAuthorizationRepository

FLOW_CONFIGURATION_READ = "flow.configuration.read"
FLOW_CONFIGURATION_WRITE = "flow.configuration.write"


class FlowConfigurationAuthorizationService:
    """Decides whether an authenticated user may read or write Flow config."""

    def __init__(
        self,
        *,
        repository: FlowExecutiveAuthorizationRepository | None = None,
        permissions: PermissionConsoleRepository | None = None,
    ) -> None:
        self._repository = repository or FlowExecutiveAuthorizationRepository()
        self._permissions = permissions or PermissionConsoleRepository()

    async def effective_permissions(
        self, conn: AsyncConnection, user_id: str
    ) -> list[str]:
        workspace_id = await self._repository.get_user_workspace_id(conn, user_id)
        if workspace_id is None:
            return []
        return await self._permissions.list_effective_permissions(
            conn, workspace_id, user_id
        )

    async def can_read(
        self, conn: AsyncConnection, user_id: str
    ) -> bool:
        permissions = await self.effective_permissions(conn, user_id)
        return FLOW_CONFIGURATION_READ in set(permissions)

    async def can_write(
        self, conn: AsyncConnection, user_id: str
    ) -> bool:
        permissions = await self.effective_permissions(conn, user_id)
        return FLOW_CONFIGURATION_WRITE in set(permissions)

    @staticmethod
    def authorized_from_permissions(
        permissions: list[str] | tuple[Any, ...],
        *,
        require_write: bool,
    ) -> bool:
        granted = set(permissions)
        capability = (
            FLOW_CONFIGURATION_WRITE if require_write else FLOW_CONFIGURATION_READ
        )
        return capability in granted
