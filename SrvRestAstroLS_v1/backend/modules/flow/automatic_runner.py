"""Finite automatic SLA check + escalation runner for Team360 Flow.

This is the minimum worker surface that lets Flow advance by itself: it runs
the deterministic first-response SLA checker and then escalates the final
breaches to the next active catalog level. It contains no business rules; the
rules live in the SLA and escalation services. A run is finite and safe to
invoke periodically from an external scheduler (cron/systemd/executor) without
changing any logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Awaitable, Callable

from psycopg_pool import AsyncConnectionPool

from .escalation_repository import FlowEscalationPostgresRepository
from .escalation_service import EscalationOutcome, FlowEscalationService
from .routing_repository import FlowRoutingPostgresRepository
from .routing_service import RoutingMessageSenderPort
from .sla_repository import FlowSLARepository
from .sla_service import FlowFirstResponseSLAService


@dataclass(frozen=True, slots=True)
class RunnerSummary:
    """Structured outcome of one automatic run (no manual log reading)."""

    scanned: int = 0
    pending: int = 0
    met: int = 0
    breached: int = 0
    reconciled: int = 0
    eligible: int = 0
    created: int = 0
    sent: int = 0
    completed: int = 0
    failed: int = 0
    idempotent: int = 0
    skipped: int = 0
    outcomes: tuple[EscalationOutcome, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "pending": self.pending,
            "met": self.met,
            "breached": self.breached,
            "reconciled": self.reconciled,
            "eligible": self.eligible,
            "created": self.created,
            "sent": self.sent,
            "completed": self.completed,
            "failed": self.failed,
            "idempotent": self.idempotent,
            "skipped": self.skipped,
            "outcomes": [asdict(outcome) for outcome in self.outcomes],
        }


class FlowAutomaticRunner:
    """Orchestrates SLA evaluation and deterministic escalation in one cycle.

    ``clock`` is injectable so tests can reproduce deadline boundary behaviour
    without sleeping. ``confirm_send`` mirrors the escalation service contract:
    False is dry-run (SLA states still advance, no escalation/email is sent),
    True performs the real next-level delivery.
    """

    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        sla_repository: FlowSLARepository,
        escalation_repository: FlowEscalationPostgresRepository,
        routing_repository: FlowRoutingPostgresRepository,
        sender: RoutingMessageSenderPort | None,
        clock: Callable[[], datetime] | None = None,
        citizen_notifier: Callable[[str], Awaitable[object]] | None = None,
    ) -> None:
        self._pool = pool
        self._sla_service = FlowFirstResponseSLAService(
            pool=pool, repository=sla_repository, clock=clock
        )
        self._escalation_service = FlowEscalationService(
            pool=pool,
            repository=escalation_repository,
            routing_repository=routing_repository,
            sender=sender,
        )
        self._citizen_notifier = citizen_notifier

    async def run_once(self, *, confirm_send: bool = False) -> RunnerSummary:
        sla = await self._sla_service.check_once()
        escalation = await self._escalation_service.escalate_once(
            confirm_send=confirm_send
        )
        if self._citizen_notifier is not None:
            # Escalation is a real continuation of the treatment: the citizen
            # receives a single generic IN_PROGRESS signal (idempotent at the
            # notification service level), never the internal reason.
            for outcome in escalation.outcomes:
                if outcome.status == "COMPLETED" and outcome.request_id:
                    await self._citizen_notifier(outcome.request_id)
        skipped = max(0, escalation.eligible - escalation.completed - escalation.failed)
        return RunnerSummary(
            scanned=sla.checked,
            pending=sla.pending,
            met=sla.met,
            breached=sla.breached,
            reconciled=sla.reconciled,
            eligible=escalation.eligible,
            created=escalation.created,
            sent=escalation.sent,
            completed=escalation.completed,
            failed=escalation.failed,
            idempotent=escalation.idempotent,
            skipped=skipped,
            outcomes=escalation.outcomes,
        )
