"""Validation and presentation service for the executive case list."""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .executive_list_repository import FlowExecutiveListPostgresRepository

LIST_STATUS_VALUES = frozenset(
    {
        "open",
        "pending_approval",
        "resolved",
        "ACTIVE",
        "CONFIRMED",
        "RESOLUTION_PENDING_APPROVAL",
        "RESOLVED",
    }
)
LIST_SLA_VALUES = frozenset({"PENDING", "MET", "BREACHED"})
MAX_PAGE_SIZE = 100


class FlowExecutiveListValidationError(ValueError):
    """Raised when list pagination or filters are outside the public contract."""


def _status_values(status: str | None) -> tuple[str, ...] | None:
    if status is None:
        return None
    if status not in LIST_STATUS_VALUES:
        raise FlowExecutiveListValidationError("status inválido")
    if status == "open":
        return ("ACTIVE", "CONFIRMED")
    if status == "pending_approval":
        return ("RESOLUTION_PENDING_APPROVAL",)
    if status == "resolved":
        return ("RESOLVED",)
    return (status,)


class FlowExecutiveListService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowExecutiveListPostgresRepository | None = None,
    ) -> None:
        self._pool = pool
        self._repository = repository or FlowExecutiveListPostgresRepository()

    async def list_cases(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        sector_id: str | None = None,
        search: str | None = None,
        sla_status: str | None = None,
        escalated: bool | None = None,
    ) -> dict[str, Any]:
        if page < 1:
            raise FlowExecutiveListValidationError("page debe ser mayor o igual a 1")
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise FlowExecutiveListValidationError(
                f"page_size debe estar entre 1 y {MAX_PAGE_SIZE}"
            )
        if sla_status is not None and sla_status not in LIST_SLA_VALUES:
            raise FlowExecutiveListValidationError("sla_status inválido")
        if search is not None:
            search = search.strip()
            if len(search) > 200:
                raise FlowExecutiveListValidationError("search supera el largo máximo")
            if not search:
                search = None
        if sector_id is not None:
            sector_id = sector_id.strip() or None

        statuses = _status_values(status)
        async with transaction(self._pool) as conn:
            rows = await self._repository.list_cases(
                conn,
                statuses=statuses,
                sector_id=sector_id,
                search=search,
                sla_status=sla_status,
                escalated=escalated,
                offset=(page - 1) * page_size,
                limit=page_size,
            )
            sectors = await self._repository.list_sector_options(conn)

        total = rows[0]["total_count"] if rows else 0
        items = [{key: value for key, value in row.items() if key != "total_count"} for row in rows]
        return {
            "items": items,
            "sectors": sectors,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_next": page * page_size < total,
            },
        }
