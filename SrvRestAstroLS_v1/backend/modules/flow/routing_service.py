"""Route confirmed Flow requests to deterministic sector Level 1 destinations."""

from __future__ import annotations

import socket
import urllib.error
from dataclasses import dataclass
from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .domain.routing import (
    INITIAL_ROUTING_LEVEL,
    ConfirmedFlowRequest,
    FlowRequestNotConfirmedError,
    FlowRequestNotFoundError,
    FlowSector,
    FlowSectorLevel,
    RoutingAssignment,
    RoutingStatus,
    resolve_sector_id,
    routing_rfc_message_id,
)
from .routing_repository import FlowRoutingPostgresRepository


class RoutingMessageSenderPort(Protocol):
    sender_address: str

    def send_message(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        rfc_message_id: str | None = None,
    ) -> str: ...

    def find_sent_message_by_rfc_message_id(
        self, rfc_message_id: str
    ) -> str | None: ...

    def find_sent_message_by_reference(
        self, reference: str, *, to: str | None = None
    ) -> str | None: ...

    def get_message_rfc_id(self, message_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class RoutingEmail:
    destination: str
    subject: str
    body: str
    rfc_message_id: str


@dataclass(frozen=True, slots=True)
class RoutingResult:
    request_id: str
    status: str
    assignment: RoutingAssignment | None
    email: RoutingEmail | None
    sent: bool = False
    reconciled: bool = False
    idempotent: bool = False
    reason_code: str | None = None


def build_routing_email(
    request: ConfirmedFlowRequest,
    sector: FlowSector,
    sector_level: FlowSectorLevel,
) -> RoutingEmail:
    location = request.location_text or "No informada"
    body = "\n".join(
        [
            "Nueva solicitud confirmada.",
            "",
            f"Caso: {request.id}",
            f"Sector: {sector.display_name}",
            f"Ubicación: {location}",
            f"Solicitud: {request.description}",
            "",
            f"Origen: {request.origin_channel.title()}",
            f"Vecino: {request.citizen_address}",
            f"Referencia externa: {request.external_thread_id}",
            f"Estado: Asignado — Nivel {sector_level.level}",
        ]
    )
    return RoutingEmail(
        destination=sector_level.destination,
        subject=(
            f"[Team360 Flow] Nueva solicitud #{request.id} — "
            f"{sector.display_name}"
        ),
        body=body,
        rfc_message_id=routing_rfc_message_id(request.id),
    )


class FlowRoutingService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowRoutingPostgresRepository,
        sender: RoutingMessageSenderPort | None,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._sender = sender

    async def route_confirmed_request(
        self, request_id: str, *, confirm_send: bool
    ) -> RoutingResult:
        async with transaction(self._pool) as conn:
            request = await self._repository.get_request(conn, request_id)
            if request is None:
                raise FlowRequestNotFoundError(f"Flow request not found: {request_id}")
            if request.status != "CONFIRMED":
                raise FlowRequestNotConfirmedError(
                    f"Flow request is not confirmed: {request_id}"
                )

            existing = await self._repository.get_assignment(conn, request_id)
            if existing is not None and existing.status == RoutingStatus.ASSIGNED:
                if (
                    confirm_send
                    and self._sender is not None
                    and existing.outbound_external_message_id
                    and not existing.outbound_observed_rfc_message_id
                ):
                    observed = _safe_observed_rfc_message_id(
                        self._sender, existing.outbound_external_message_id
                    )
                    if observed:
                        existing = await self._repository.record_observed_rfc_message_id(
                            conn,
                            assignment_id=existing.id,
                            observed_rfc_message_id=observed,
                        )
                await self._repository.ensure_work_state(conn, existing)
                return RoutingResult(
                    request_id=request.id,
                    status=existing.status.value,
                    assignment=existing,
                    email=None,
                    idempotent=True,
                )
            if existing is not None and existing.status == RoutingStatus.ROUTING_UNRESOLVED:
                return RoutingResult(
                    request_id=request.id,
                    status=existing.status.value,
                    assignment=existing,
                    email=None,
                    idempotent=True,
                    reason_code=existing.last_error_code,
                )

            sector_id = resolve_sector_id(request.tentative_category)
            if sector_id is None:
                assignment = await self._repository.create_unresolved_assignment(
                    conn,
                    request_id=request.id,
                    sector_id=None,
                    error_code="CATEGORY_UNRESOLVED",
                )
                return RoutingResult(
                    request.id,
                    assignment.status.value,
                    assignment,
                    None,
                    reason_code="CATEGORY_UNRESOLVED",
                )

            sector = await self._repository.get_sector(conn, sector_id)
            if sector is None or not sector.active:
                assignment = await self._repository.create_unresolved_assignment(
                    conn,
                    request_id=request.id,
                    sector_id=sector_id if sector else None,
                    error_code="SECTOR_INACTIVE" if sector else "SECTOR_NOT_FOUND",
                )
                return RoutingResult(
                    request.id,
                    assignment.status.value,
                    assignment,
                    None,
                    reason_code=assignment.last_error_code,
                )

            sector_level = await self._repository.get_sector_level(
                conn, sector.sector_id, INITIAL_ROUTING_LEVEL
            )
            if sector_level is None or not sector_level.active:
                assignment = await self._repository.create_unresolved_assignment(
                    conn,
                    request_id=request.id,
                    sector_id=sector.sector_id,
                    error_code=(
                        "LEVEL_INACTIVE" if sector_level else "LEVEL_NOT_FOUND"
                    ),
                )
                return RoutingResult(
                    request.id,
                    assignment.status.value,
                    assignment,
                    None,
                    reason_code=assignment.last_error_code,
                )

            email = build_routing_email(request, sector, sector_level)
            if not confirm_send:
                return RoutingResult(request.id, "DRY_RUN", None, email)

            assignment = existing or await self._repository.create_pending_assignment(
                conn,
                request_id=request.id,
                sector=sector,
                sector_level=sector_level,
                outbound_rfc_message_id=email.rfc_message_id,
            )
            if assignment.status == RoutingStatus.ASSIGNED:
                return RoutingResult(
                    request.id,
                    assignment.status.value,
                    assignment,
                    None,
                    idempotent=True,
                )
            if self._sender is None:
                raise RuntimeError("Routing sender is required when confirm_send is true.")

            assignment = await self._repository.mark_attempt(conn, assignment.id)
            try:
                recovered_message_id = (
                    self._sender.find_sent_message_by_rfc_message_id(
                        email.rfc_message_id
                    )
                    or self._sender.find_sent_message_by_reference(
                        request.id, to=email.destination
                    )
                )
                if recovered_message_id:
                    observed = _safe_observed_rfc_message_id(
                        self._sender, recovered_message_id
                    )
                    assigned = await self._repository.mark_assigned(
                        conn,
                        assignment_id=assignment.id,
                        external_message_id=recovered_message_id,
                        observed_rfc_message_id=observed,
                    )
                    await self._repository.ensure_work_state(conn, assigned)
                    return RoutingResult(
                        request.id,
                        assigned.status.value,
                        assigned,
                        email,
                        reconciled=True,
                        idempotent=True,
                    )
                external_message_id = self._sender.send_message(
                    to=email.destination,
                    subject=email.subject,
                    body=email.body,
                    rfc_message_id=email.rfc_message_id,
                )
                observed_rfc_message_id = _safe_observed_rfc_message_id(
                    self._sender, external_message_id
                )
            except Exception as exc:
                failed = await self._repository.mark_failed(
                    conn,
                    assignment_id=assignment.id,
                    error_code=type(exc).__name__,
                    delivery_uncertain=(
                        assignment.delivery_uncertain
                        or _delivery_is_uncertain(exc)
                    ),
                )
                return RoutingResult(
                    request.id,
                    failed.status.value,
                    failed,
                    email,
                    reason_code=failed.last_error_code,
                )

            assigned = await self._repository.mark_assigned(
                conn,
                assignment_id=assignment.id,
                external_message_id=external_message_id,
                observed_rfc_message_id=observed_rfc_message_id,
            )
            await self._repository.ensure_work_state(conn, assigned)
            return RoutingResult(
                request.id,
                assigned.status.value,
                assigned,
                email,
                sent=True,
            )


def _delivery_is_uncertain(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    return isinstance(exc, urllib.error.URLError) and isinstance(
        exc.reason, (TimeoutError, socket.timeout)
    )


def _safe_observed_rfc_message_id(
    sender: RoutingMessageSenderPort, external_message_id: str
) -> str | None:
    try:
        return sender.get_message_rfc_id(external_message_id)
    except Exception:
        return None
