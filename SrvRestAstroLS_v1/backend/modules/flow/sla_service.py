"""Deterministic first-response SLA evaluation use case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .domain import FirstResponseSLAStatus, evaluate_first_response_sla
from .sla_repository import FlowSLARepository


@dataclass(frozen=True, slots=True)
class SLACheckSummary:
    checked: int = 0
    pending: int = 0
    met: int = 0
    breached: int = 0
    reconciled: int = 0


class FlowFirstResponseSLAService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowSLARepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def check_once(self) -> SLACheckSummary:
        now = self._clock()
        counts = {status.value.lower(): 0 for status in FirstResponseSLAStatus}
        checked = 0
        reconciled_count = 0
        async with transaction(self._pool) as conn:
            for sla in await self._repository.list_evaluable(conn):
                evaluation = evaluate_first_response_sla(
                    current_status=sla.status,
                    due_at=sla.due_at,
                    first_response_at=sla.first_response_at,
                    now=now,
                )
                await self._repository.persist_evaluation(
                    conn,
                    sla=sla,
                    status=evaluation.status,
                    now=now,
                    reconciled=evaluation.reconciled,
                )
                checked += 1
                counts[evaluation.status.value.lower()] += 1
                reconciled_count += int(evaluation.reconciled)
        return SLACheckSummary(
            checked=checked,
            pending=counts["pending"],
            met=counts["met"],
            breached=counts["breached"],
            reconciled=reconciled_count,
        )
