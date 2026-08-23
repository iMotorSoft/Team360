"""Litestar route handlers owned by Team360 Flow.

Flow exposes finite CLI operations, the read-only executive audit query and
the sector configuration management API. Access is resolved centrally through
``_require_flow_actor``:

- default_admin mode (MVP): no token is required; every visitor is the
  implicit ``administrator`` with all Flow capabilities.
- authenticated mode: the console PASETO token is verified and the persistent
  capabilities are enforced fail-closed:

  - ``flow.executive.read`` for the executive audit query
  - ``flow.configuration.read`` / ``flow.configuration.write`` for sector
    configuration

Authorization happens before any data access or mutation.
"""

from __future__ import annotations

from typing import Any

from litestar import get, patch
from litestar.connection import Request
from litestar.exceptions import HTTPException
from litestar.status_codes import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_ENTITY,
)

from modules.console.auth import (
    ConsoleAuthError,
    extract_bearer_token,
    verify_console_access_token,
)
from modules.db.pool import get_pool
from modules.db.transaction import transaction
from modules.security.paseto_tokens import get_dev_public_keys_by_id, paseto_console_settings_from_env

from .access_mode import (
    AUTHENTICATED_MODE,
    FLOW_CONFIGURATION_READ,
    FLOW_CONFIGURATION_WRITE,
    FLOW_EXECUTIVE_READ,
    FlowActor,
    default_admin_actor,
    flow_access_mode,
)
from .audit_repository import FlowAuditRepository
from .closure_repository import FlowClosurePostgresRepository
from .configuration_auth import FlowConfigurationAuthorizationService
from .configuration_service import (
    FlowConfigurationService,
    FlowConfigurationValidationError,
    FlowSectorNotFoundError,
)
from .domain import FlowRequestNotFoundError
from .executive_ai import LiteLLMExecutiveInterpreter
from .executive_auth import FlowExecutiveAuthorizationService
from .executive_list_service import (
    FlowExecutiveListService,
    FlowExecutiveListValidationError,
)
from .executive_service import (
    FlowAuditIntegrityError,
    FlowExecutiveAuditService,
)

_FLOW_CAPABILITIES = {
    FLOW_EXECUTIVE_READ,
    FLOW_CONFIGURATION_READ,
    FLOW_CONFIGURATION_WRITE,
}


def _resolve_public_keys(settings: object) -> dict[str, str]:
    public_pem: str | None = getattr(settings, "public_key_pem", None)
    if public_pem:
        return {getattr(settings, "key_id", "console-key"): public_pem}
    return get_dev_public_keys_by_id()


def _authorization_service() -> FlowExecutiveAuthorizationService:
    return FlowExecutiveAuthorizationService()


def _executive_service(
    pool: Any, question: str | None
) -> FlowExecutiveAuditService:
    return FlowExecutiveAuditService(
        pool=pool,
        closure_repository=FlowClosurePostgresRepository(),
        audit_repository=FlowAuditRepository(),
        interpreter=LiteLLMExecutiveInterpreter() if question else None,
    )


def _executive_list_service(pool: Any) -> FlowExecutiveListService:
    return FlowExecutiveListService(pool=pool)


def _configuration_authorization_service() -> FlowConfigurationAuthorizationService:
    return FlowConfigurationAuthorizationService()


def _configuration_service(pool: Any) -> FlowConfigurationService:
    return FlowConfigurationService(pool=pool)


def _authenticate(request: Request | None) -> str:
    """Return the authenticated user_id or raise 401."""
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
        principal = verify_console_access_token(
            token,
            public_keys_by_id=_resolve_public_keys(settings),
            issuer=settings.issuer,
        )
    except ConsoleAuthError as exc:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(exc))
    return principal.user_id


async def _require_flow_actor(
    request: Request | None,
    *,
    capability: str,
    write: bool = False,
) -> FlowActor:
    """Resolve the Flow actor for the request, fail closed.

    In default_admin mode the actor is the implicit administrator with every
    Flow capability. In authenticated mode the token is verified and the
    requested capability is enforced before any data access.
    """
    mode = flow_access_mode()
    if mode == AUTHENTICATED_MODE:
        if capability not in _FLOW_CAPABILITIES:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")
        user_id = _authenticate(request)
        pool = get_pool()
        if capability in {FLOW_CONFIGURATION_READ, FLOW_CONFIGURATION_WRITE}:
            authorization_service = _configuration_authorization_service()
            async with transaction(pool) as conn:
                authorized = (
                    await authorization_service.can_write(conn, user_id)
                    if write
                    else await authorization_service.can_read(conn, user_id)
                )
        else:
            authorization_service = _authorization_service()
            async with transaction(pool) as conn:
                authorized = await authorization_service.has_flow_executive_read(
                    conn, user_id
                )
        if not authorized:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden")
        return FlowActor(
            role="member",
            user_id=user_id,
            capabilities=frozenset({capability}),
        )
    # default_admin (and any future permissive mode): implicit administrator.
    return default_admin_actor()


@get("/api/team360-flow/executive/{request_id:str}")
async def executive_audit_query(
    request_id: str,
    request: Request | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Executive case query, accessible to the default administrator."""
    await _require_flow_actor(request, capability=FLOW_EXECUTIVE_READ)
    pool = get_pool()
    service = _executive_service(pool, question)
    try:
        return await service.query_case(request_id, question=question)
    except FlowRequestNotFoundError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc))
    except FlowAuditIntegrityError as exc:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT, detail=str(exc)
        )


@get("/api/team360-flow/executive")
async def executive_case_list(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    sector_id: str | None = None,
    search: str | None = None,
    sla_status: str | None = None,
    escalated: bool | None = None,
    request: Request | None = None,
) -> dict[str, Any]:
    """Read-only executive summaries for the Directorio list."""
    await _require_flow_actor(request, capability=FLOW_EXECUTIVE_READ)
    pool = get_pool()
    try:
        return await _executive_list_service(pool).list_cases(
            page=page,
            page_size=page_size,
            status=status,
            sector_id=sector_id,
            search=search,
            sla_status=sla_status,
            escalated=escalated,
        )
    except FlowExecutiveListValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


@get("/api/team360-flow/configuration")
async def flow_configuration_list(
    request: Request | None = None,
) -> dict[str, Any]:
    """List of sector configurations, accessible to the default administrator."""
    await _require_flow_actor(request, capability=FLOW_CONFIGURATION_READ)
    pool = get_pool()
    service = _configuration_service(pool)
    return await service.list_configurations()


@get("/api/team360-flow/configuration/{sector_id:str}")
async def flow_configuration_get(
    sector_id: str,
    request: Request | None = None,
) -> dict[str, Any]:
    """One sector configuration, accessible to the default administrator."""
    await _require_flow_actor(request, capability=FLOW_CONFIGURATION_READ)
    pool = get_pool()
    service = _configuration_service(pool)
    configuration = await service.get_configuration(sector_id)
    if configuration is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Flow sector not found: {sector_id}",
        )
    return configuration


@patch("/api/team360-flow/configuration/{sector_id:str}")
async def flow_configuration_update(
    sector_id: str,
    data: dict[str, Any],
    request: Request | None = None,
) -> dict[str, Any]:
    """Atomic sector configuration update, writable by the default admin."""
    await _require_flow_actor(
        request, capability=FLOW_CONFIGURATION_WRITE, write=True
    )

    unknown_fields = set(data) - {"levels", "closure_approval_level"}
    if unknown_fields:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"campos no permitidos: {sorted(unknown_fields)}",
        )
    if "levels" not in data or "closure_approval_level" not in data:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail="se requieren levels y closure_approval_level",
        )

    pool = get_pool()
    service = _configuration_service(pool)
    try:
        configuration = await service.update_configuration(
            sector_id,
            levels=data["levels"],
            closure_approval_level=data["closure_approval_level"],
        )
    except FlowSectorNotFoundError as exc:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=str(exc))
    except FlowConfigurationValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    assert configuration is not None
    return configuration


# --- Operational settings endpoints ---


@get("/api/team360-flow/operational-settings")
async def flow_operational_settings_get(
    request: Request | None = None,
) -> dict[str, Any]:
    """Read Flow operational settings (automation, scheduler, intake)."""
    await _require_flow_actor(request, capability=FLOW_CONFIGURATION_READ)
    pool = get_pool()
    service = _configuration_service(pool)
    return await service.get_operational_settings()


@patch("/api/team360-flow/operational-settings")
async def flow_operational_settings_update(
    data: dict[str, Any],
    request: Request | None = None,
) -> dict[str, Any]:
    """Update Flow operational settings."""
    await _require_flow_actor(
        request, capability=FLOW_CONFIGURATION_WRITE, write=True
    )

    allowed = {
        "automation_enabled",
        "scheduler_interval_seconds",
        "mail_intake_enabled",
        "mail_batch_limit",
        "mail_after_cutoff",
        "mail_cutoff_epoch",
    }
    unknown_fields = set(data) - allowed
    if unknown_fields:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"campos no permitidos: {sorted(unknown_fields)}",
        )

    pool = get_pool()
    service = _configuration_service(pool)
    try:
        return await service.update_operational_settings(
            automation_enabled=data.get("automation_enabled"),
            scheduler_interval_seconds=data.get("scheduler_interval_seconds"),
            mail_intake_enabled=data.get("mail_intake_enabled"),
            mail_batch_limit=data.get("mail_batch_limit"),
            mail_after_cutoff=data.get("mail_after_cutoff"),
            mail_cutoff_epoch=data.get("mail_cutoff_epoch"),
        )
    except FlowConfigurationValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


# --- Scheduler status endpoint ---


@get("/api/team360-flow/scheduler/status")
async def flow_scheduler_status(
    request: Request | None = None,
) -> dict[str, Any]:
    """Return scheduler execution state from PostgreSQL."""
    await _require_flow_actor(request, capability=FLOW_CONFIGURATION_READ)
    from .operational_settings_repository import (
        FlowSchedulerStateRepository,
    )

    pool = get_pool()
    repo = FlowSchedulerStateRepository()
    async with transaction(pool) as conn:
        state = await repo.get_state(conn)
    return {
        "last_started_at_utc": state.get("last_started_at_utc"),
        "last_finished_at_utc": state.get("last_finished_at_utc"),
        "last_result": state.get("last_result"),
        "last_error_class": state.get("last_error_class"),
        "processed_count": state.get("processed_count", 0),
        "cycle_count": state.get("cycle_count", 0),
    }


ROUTE_HANDLERS: tuple[Any, ...] = (
    executive_audit_query,
    executive_case_list,
    flow_configuration_list,
    flow_configuration_get,
    flow_configuration_update,
    flow_operational_settings_get,
    flow_operational_settings_update,
    flow_scheduler_status,
)
