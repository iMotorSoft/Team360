"""Console bootstrap endpoint (/api/console/bootstrap).

Experimental: returns ConsoleBootstrap + PASETO access_token when
TEAM360_PASETO_ENABLED=true.

Preserves full compatibility: existing fields unchanged, token fields
(access_token, token_type, expires_in) returned only when PASETO is enabled.
"""

from __future__ import annotations

from typing import Any

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from modules.console.service import ConsoleBootstrapService
from modules.console.errors import (
    ConsoleBootstrapError,
)
from modules.db.errors import DatabasePoolNotInitializedError
from modules.db.pool import get_pool
from modules.security.paseto_tokens import paseto_console_settings_from_env

_SERVICE = ConsoleBootstrapService()


@post("/api/console/bootstrap")
async def console_bootstrap(
    data: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = data.get("workspace_id", "")
    user_id = data.get("user_id", "")

    if not workspace_id or not user_id:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="workspace_id and user_id are required.",
        )

    paseto_settings = paseto_console_settings_from_env()

    try:
        pool = get_pool()
    except DatabasePoolNotInitializedError:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database pool not available.",
        )

    try:
        async with pool.connection() as conn:
            bootstrap = await _SERVICE.build_bootstrap(
                conn,
                workspace_id,
                user_id,
                paseto_settings=paseto_settings if paseto_settings.enabled else None,
            )
    except ConsoleBootstrapError as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return _bootstrap_to_dict(bootstrap)


def _bootstrap_to_dict(bootstrap: Any) -> dict[str, Any]:
    return {
        "workspace": bootstrap.workspace,
        "current_user": bootstrap.current_user,
        "effective_permissions": bootstrap.effective_permissions,
        "capabilities": bootstrap.capabilities,
        "entitlements": bootstrap.entitlements,
        "navigation": bootstrap.navigation,
        "services": bootstrap.services,
        "tasks_summary": bootstrap.tasks_summary,
        "alerts": bootstrap.alerts,
        "workspace_context": bootstrap.workspace_context,
        "organization_context": bootstrap.organization_context,
        "debug": bootstrap.debug,
        "access_token": bootstrap.access_token,
        "token_type": bootstrap.token_type,
        "expires_in": bootstrap.expires_in,
    }
