"""Litestar route handlers owned by Team360 Flow.

Flow exposes finite CLI operations and the read-only executive audit query.
Handlers are added here and included in ``ROUTE_HANDLERS``; the module registry
and entrypoint are not modified per endpoint.
"""

from __future__ import annotations

from typing import Any

from litestar import get
from litestar.connection import Request
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND

from modules.console.auth import (
    ConsoleAuthError,
    extract_bearer_token,
    verify_console_access_token,
)
from modules.db.pool import get_pool
from modules.security.paseto_tokens import get_dev_public_keys_by_id, paseto_console_settings_from_env

from .audit_repository import FlowAuditRepository
from .closure_repository import FlowClosurePostgresRepository
from .domain import FlowRequestNotFoundError
from .executive_ai import LiteLLMExecutiveInterpreter
from .executive_service import FlowExecutiveAuditService


def _resolve_public_keys(settings: object) -> dict[str, str]:
    public_pem: str | None = getattr(settings, "public_key_pem", None)
    if public_pem:
        return {getattr(settings, "key_id", "console-key"): public_pem}
    return get_dev_public_keys_by_id()


@get("/api/team360-flow/executive/{request_id:str}")
async def executive_audit_query(
    request_id: str,
    request: Request | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Read-only executive case query, authenticated with the console PASETO token."""
    if request is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )

    authorization = request.headers.get("Authorization")
    try:
        token = extract_bearer_token(authorization)
    except ConsoleAuthError as exc:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(exc))

    settings = paseto_console_settings_from_env()
    try:
        verify_console_access_token(
            token,
            public_keys_by_id=_resolve_public_keys(settings),
            issuer=settings.issuer,
        )
    except ConsoleAuthError as exc:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(exc))

    service = FlowExecutiveAuditService(
        pool=get_pool(),
        closure_repository=FlowClosurePostgresRepository(),
        audit_repository=FlowAuditRepository(),
        interpreter=LiteLLMExecutiveInterpreter() if question else None,
    )
    try:
        return await service.query_case(request_id, question=question)
    except FlowRequestNotFoundError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc))


ROUTE_HANDLERS: tuple[Any, ...] = (executive_audit_query,)
