"""Escalate final Level 1 first-response breaches to the catalogued Level 2."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .domain import EscalationCandidate, EscalationStatus, RoutingStatus
from .domain.routing import routing_rfc_message_id
from .escalation_repository import FlowEscalationPostgresRepository
from .routing_repository import FlowRoutingPostgresRepository
from .routing_service import (
    RoutingEmail,
    RoutingMessageSenderPort,
    _delivery_is_uncertain,
    _safe_observed_rfc_message_id,
)


def escalation_routing_key(sector_id: str, level: int) -> str:
    return f"{sector_id}_level_{level}"


def build_escalation_email(
    candidate: EscalationCandidate, destination: str
) -> RoutingEmail:
    first_response = (
        candidate.first_response_at.isoformat()
        if candidate.first_response_at is not None
        else "Sin respuesta"
    )
    to_level = candidate.from_level + 1
    routing_key = escalation_routing_key(candidate.sector_id, to_level)
    body = "\n".join(
        [
            f"Solicitud escalada a Nivel {to_level}.",
            "",
            f"Caso: {candidate.request_id}",
            f"Sector: {candidate.sector_display_name}",
            f"Nivel actual: {to_level}",
            "",
            "Solicitud confirmada:",
            candidate.description,
            "",
            "Ubicación:",
            candidate.location_text or "No informada",
            "",
            "Motivo del escalamiento:",
            f"SLA de primera respuesta de Nivel {candidate.from_level} vencido.",
            "",
            f"Origen: {candidate.origin_channel.title()}",
            f"Nivel anterior: {candidate.sector_display_name} N{candidate.from_level}",
            f"Destino N{candidate.from_level}: {candidate.from_destination}",
            f"Asignado N{candidate.from_level}: {candidate.from_assigned_at.isoformat()}",
            f"Vencimiento N{candidate.from_level}: {candidate.sla_due_at.isoformat()}",
            f"Primera respuesta N{candidate.from_level}: {first_response}",
            f"Resultado SLA N{candidate.from_level}: {candidate.sla_status}",
        ]
    )
    return RoutingEmail(
        destination=destination,
        subject=(
            f"[Team360 Flow][ESCALADO][R:{routing_key}][{candidate.request_id}] "
            f"{candidate.sector_display_name} — Nivel {to_level}"
        ),
        body=body,
        rfc_message_id=routing_rfc_message_id(candidate.request_id, routing_key),
    )


@dataclass(frozen=True, slots=True)
class EscalationOutcome:
    request_id: str
    trigger_sla_id: str
    status: str
    escalation_id: str | None = None
    routing_id: str | None = None
    destination: str | None = None
    external_message_id: str | None = None
    created: bool = False
    sent: bool = False
    reconciled: bool = False
    idempotent: bool = False
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class EscalationSummary:
    eligible: int
    created: int
    sent: int
    completed: int
    failed: int
    idempotent: int
    outcomes: tuple[EscalationOutcome, ...]


class FlowEscalationService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowEscalationPostgresRepository,
        routing_repository: FlowRoutingPostgresRepository,
        sender: RoutingMessageSenderPort | None,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._routing_repository = routing_repository
        self._sender = sender

    async def escalate_once(self, *, confirm_send: bool) -> EscalationSummary:
        async with transaction(self._pool) as conn:
            candidates = await self._repository.list_eligible(conn)
        if not confirm_send:
            outcomes = []
            for candidate in candidates:
                level = await self._get_active_next_level(candidate)
                outcomes.append(
                    EscalationOutcome(
                        candidate.request_id,
                        candidate.trigger_sla_id,
                        "DRY_RUN",
                        destination=level.destination if level is not None else None,
                        reason_code=(
                            None if level is not None else "NEXT_LEVEL_UNAVAILABLE"
                        ),
                    )
                )
            return EscalationSummary(len(candidates), 0, 0, 0, 0, 0, tuple(outcomes))

        outcomes = []
        for candidate in candidates:
            outcomes.append(await self._escalate(candidate.trigger_sla_id))
        return EscalationSummary(
            eligible=len(candidates),
            created=sum(outcome.created for outcome in outcomes),
            sent=sum(outcome.sent for outcome in outcomes),
            completed=sum(outcome.status == "COMPLETED" for outcome in outcomes),
            failed=sum(outcome.status == "FAILED" for outcome in outcomes),
            idempotent=sum(outcome.idempotent for outcome in outcomes),
            outcomes=tuple(outcomes),
        )

    async def _get_active_next_level(self, candidate: EscalationCandidate):
        async with transaction(self._pool) as conn:
            level = await self._routing_repository.get_sector_level(
                conn, candidate.sector_id, candidate.from_level + 1
            )
            return level if level is not None and level.active else None

    async def _escalate(self, trigger_sla_id: str) -> EscalationOutcome:
        async with transaction(self._pool) as conn:
            # This locked reread is the final anti-false-escalation gate. A
            # timely first response makes the candidate disappear even if an
            # earlier checker had persisted a provisional BREACHED result.
            candidate = await self._repository.get_eligible(conn, trigger_sla_id)
            if candidate is None:
                existing = await self._repository.get_by_trigger(conn, trigger_sla_id)
                return EscalationOutcome(
                    "",
                    trigger_sla_id,
                    existing.status.value if existing else "NOT_ELIGIBLE",
                    escalation_id=existing.id if existing else None,
                    routing_id=existing.to_routing_id if existing else None,
                    idempotent=existing is not None,
                    reason_code="ALREADY_ESCALATED" if existing else "SLA_NOT_ELIGIBLE",
                )

            sector = await self._routing_repository.get_sector(
                conn, candidate.sector_id
            )
            next_level = await self._routing_repository.get_sector_level(
                conn, candidate.sector_id, candidate.from_level + 1
            )
            if (
                sector is None
                or not sector.active
                or next_level is None
                or not next_level.active
            ):
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "NOT_ELIGIBLE",
                    reason_code="NEXT_LEVEL_UNAVAILABLE",
                )

            existing_escalation = await self._repository.get_by_trigger(
                conn, trigger_sla_id
            )
            escalation = existing_escalation or await self._repository.create_pending(
                conn, candidate
            )
            created = existing_escalation is None
            if escalation.status == EscalationStatus.COMPLETED:
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "COMPLETED",
                    escalation_id=escalation.id,
                    routing_id=escalation.to_routing_id,
                    created=created,
                    idempotent=True,
                    reason_code="ALREADY_ESCALATED",
                )

            routing_key = escalation_routing_key(candidate.sector_id, next_level.level)
            email = build_escalation_email(candidate, next_level.destination)
            assignment = await self._routing_repository.get_assignment_for_key(
                conn, request_id=candidate.request_id, routing_key=routing_key
            )
            assignment = (
                assignment
                or await self._routing_repository.create_pending_assignment_for_level(
                    conn,
                    request_id=candidate.request_id,
                    routing_key=routing_key,
                    sector=sector,
                    sector_level=next_level,
                    outbound_rfc_message_id=email.rfc_message_id,
                )
            )
            if assignment.status == RoutingStatus.ASSIGNED:
                await self._routing_repository.ensure_work_state(conn, assignment)
                escalation = await self._repository.mark_completed(
                    conn, escalation_id=escalation.id, to_routing_id=assignment.id
                )
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "COMPLETED",
                    escalation_id=escalation.id,
                    routing_id=assignment.id,
                    destination=assignment.destination,
                    external_message_id=assignment.outbound_external_message_id,
                    created=created,
                    idempotent=True,
                )
            if self._sender is None:
                raise RuntimeError("Escalation sender is required for real delivery.")

            assignment = await self._routing_repository.mark_attempt(conn, assignment.id)
            try:
                recovered = (
                    self._sender.find_sent_message_by_rfc_message_id(email.rfc_message_id)
                    or self._sender.find_sent_message_by_reference(
                        candidate.request_id, to=email.destination
                    )
                )
            except Exception as exc:
                failed = await self._routing_repository.mark_failed(
                    conn,
                    assignment_id=assignment.id,
                    error_code=type(exc).__name__,
                    delivery_uncertain=True,
                )
                await self._repository.mark_failed(
                    conn, escalation_id=escalation.id, error_code=type(exc).__name__
                )
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "FAILED",
                    escalation_id=escalation.id,
                    routing_id=failed.id,
                    destination=email.destination,
                    created=created,
                    reason_code=type(exc).__name__,
                )

            if recovered:
                observed = _safe_observed_rfc_message_id(self._sender, recovered)
                assigned = await self._routing_repository.mark_assigned(
                    conn,
                    assignment_id=assignment.id,
                    external_message_id=recovered,
                    observed_rfc_message_id=observed,
                )
                await self._routing_repository.ensure_work_state(conn, assigned)
                completed = await self._repository.mark_completed(
                    conn, escalation_id=escalation.id, to_routing_id=assigned.id
                )
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "COMPLETED",
                    escalation_id=completed.id,
                    routing_id=assigned.id,
                    destination=email.destination,
                    external_message_id=recovered,
                    created=created,
                    reconciled=True,
                    idempotent=True,
                )

            if assignment.delivery_uncertain:
                await self._repository.mark_failed(
                    conn,
                    escalation_id=escalation.id,
                    error_code="DELIVERY_UNCERTAIN_NOT_RECONCILED",
                )
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "FAILED",
                    escalation_id=escalation.id,
                    routing_id=assignment.id,
                    destination=email.destination,
                    created=created,
                    reason_code="DELIVERY_UNCERTAIN_NOT_RECONCILED",
                )

            try:
                external_id = self._sender.send_message(
                    to=email.destination,
                    subject=email.subject,
                    body=email.body,
                    rfc_message_id=email.rfc_message_id,
                )
                observed = _safe_observed_rfc_message_id(self._sender, external_id)
            except Exception as exc:
                failed = await self._routing_repository.mark_failed(
                    conn,
                    assignment_id=assignment.id,
                    error_code=type(exc).__name__,
                    delivery_uncertain=_delivery_is_uncertain(exc),
                )
                await self._repository.mark_failed(
                    conn, escalation_id=escalation.id, error_code=type(exc).__name__
                )
                return EscalationOutcome(
                    candidate.request_id,
                    trigger_sla_id,
                    "FAILED",
                    escalation_id=escalation.id,
                    routing_id=failed.id,
                    destination=email.destination,
                    created=created,
                    reason_code=type(exc).__name__,
                )

            assigned = await self._routing_repository.mark_assigned(
                conn,
                assignment_id=assignment.id,
                external_message_id=external_id,
                observed_rfc_message_id=observed,
            )
            await self._routing_repository.ensure_work_state(conn, assigned)
            completed = await self._repository.mark_completed(
                conn, escalation_id=escalation.id, to_routing_id=assigned.id
            )
            return EscalationOutcome(
                candidate.request_id,
                trigger_sla_id,
                "COMPLETED",
                escalation_id=completed.id,
                routing_id=assigned.id,
                destination=email.destination,
                external_message_id=external_id,
                created=created,
                sent=True,
            )
