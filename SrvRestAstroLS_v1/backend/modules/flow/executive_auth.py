"""Minimal Directorio authorization guard for the Flow executive query.

Separates AUTHENTICATION (PASETO proves identity) from AUTHORIZATION (the
capability ``flow.executive.read`` resolved from the persistent RBAC). Fail
closed: any user without the explicit capability is denied, regardless of
email domain or client-supplied claims.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from modules.console.repositories import PermissionConsoleRepository
from modules.db.transaction import fetch_one

FLOW_EXECUTIVE_READ = "flow.executive.read"


class FlowExecutiveAuthorizationRepository:
    async def get_user_workspace_id(
        self, conn: AsyncConnection, user_id: str
    ) -> str | None:
        row = await fetch_one(
            conn,
            """
            select workspace_id::text as workspace_id
            from core_users
            where id = %(user_id)s::uuid
            """,
            {"user_id": user_id},
        )
        return row["workspace_id"] if row else None


class FlowExecutiveAuthorizationService:
    """Decides whether an authenticated user may read Flow executive data."""

    def __init__(
        self,
        *,
        repository: FlowExecutiveAuthorizationRepository | None = None,
        permissions: PermissionConsoleRepository | None = None,
    ) -> None:
        self._repository = repository or FlowExecutiveAuthorizationRepository()
        self._permissions = permissions or PermissionConsoleRepository()

    async def has_flow_executive_read(
        self, conn: AsyncConnection, user_id: str
    ) -> bool:
        workspace_id = await self._repository.get_user_workspace_id(conn, user_id)
        if workspace_id is None:
            return False
        permissions = await self._permissions.list_effective_permissions(
            conn, workspace_id, user_id
        )
        return FLOW_EXECUTIVE_READ in permissions

    async def effective_permissions(
        self, conn: AsyncConnection, user_id: str
    ) -> list[str]:
        workspace_id = await self._repository.get_user_workspace_id(conn, user_id)
        if workspace_id is None:
            return []
        return await self._permissions.list_effective_permissions(
            conn, workspace_id, user_id
        )

    @staticmethod
    def authorized_from_permissions(permissions: list[str] | tuple[Any, ...]) -> bool:
        return FLOW_EXECUTIVE_READ in set(permissions)
