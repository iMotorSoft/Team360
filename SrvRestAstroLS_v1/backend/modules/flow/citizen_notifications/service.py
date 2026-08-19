"""Citizen notification service: minimal, safe, idempotent public messages.

Each notification is persisted as a trace with a deterministic request+type
dedupe key, sent through the existing messaging abstraction and reconciled
against the provider before any retry so an uncertain delivery never produces
a duplicate email. A delivery failure never affects the underlying Flow case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .domain import (
    CitizenCaseProjection,
    CitizenDeliveryStatus,
    CitizenNotificationType,
    PublicStatus,
    citizen_rfc_message_id,
    dedupe_key,
    map_internal_to_public,
    public_reference_for,
    public_state_for_notification_type,
    render_notification,
)
from .repository import CitizenNotificationPostgresRepository
from ..routing_service import (
    RoutingMessageSenderPort,
    _delivery_is_uncertain,
    _safe_observed_rfc_message_id,
)

_CHANNEL = "email"


@dataclass(frozen=True, slots=True)
class CitizenNotifyResult:
    request_id: str
    notification_type: CitizenNotificationType
    outcome: str
    trace_id: str | None = None
    provider_message_id: str | None = None


class FlowCitizenNotificationService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: CitizenNotificationPostgresRepository,
        sender: RoutingMessageSenderPort | None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._sender = sender
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Public entry points (all idempotent).
    # ------------------------------------------------------------------
    async def notify_received(self, request_id: str) -> CitizenNotifyResult:
        return await self._deliver(
            request_id, CitizenNotificationType.CITIZEN_RECEIVED
        )

    async def notify_received_for_conversation(
        self, conversation_id: str
    ) -> list[CitizenNotifyResult]:
        async with transaction(self._pool) as conn:
            request_ids = await self._repository.find_confirmed_request_ids(
                conn, conversation_id
            )
        results: list[CitizenNotifyResult] = []
        for request_id in request_ids:
            results.append(
                await self._deliver(
                    request_id, CitizenNotificationType.CITIZEN_RECEIVED
                )
            )
        return results

    async def notify_in_progress(self, request_id: str) -> CitizenNotifyResult:
        return await self._deliver(
            request_id, CitizenNotificationType.CITIZEN_IN_PROGRESS
        )

    async def notify_resolved(self, request_id: str) -> CitizenNotifyResult:
        return await self._deliver(
            request_id, CitizenNotificationType.CITIZEN_RESOLVED
        )

    # ------------------------------------------------------------------
    # Delivery pipeline.
    # ------------------------------------------------------------------
    async def _deliver(
        self,
        request_id: str,
        notification_type: CitizenNotificationType,
    ) -> CitizenNotifyResult:
        if self._sender is None:
            return CitizenNotifyResult(
                request_id, notification_type, "NO_SENDER"
            )
        sender = self._sender
        async with transaction(self._pool) as conn:
            projection_row = await self._repository.get_request_projection(
                conn, request_id
            )
            if projection_row is None:
                return CitizenNotifyResult(
                    request_id, notification_type, "REQUEST_NOT_FOUND"
                )
            public_status = map_internal_to_public(
                projection_row["request_status"]
            )
            if public_status is None:
                return CitizenNotifyResult(
                    request_id, notification_type, "NOT_ELIGIBLE"
                )
            # Deterministic per-type guard.
            #
            # - RECEIVED only after the request really exists (CONFIRMED).
            # - RESOLVED only after an APPROVED closure (request RESOLVED,
            #   terminal).
            # - IN_PROGRESS is a transition signal fired by a real operational
            #   event (first response or escalation); it is never emitted once
            #   the case is closed, and the request-level status stays CONFIRMED
            #   during active treatment, so any non-terminal state is eligible.
            if notification_type is CitizenNotificationType.CITIZEN_IN_PROGRESS:
                if public_status is PublicStatus.RESOLVED:
                    return CitizenNotifyResult(
                        request_id, notification_type, "STATUS_MISMATCH"
                    )
            elif (
                public_status
                is not public_state_for_notification_type(notification_type)
            ):
                return CitizenNotifyResult(
                    request_id, notification_type, "STATUS_MISMATCH"
                )

            existing = await self._repository.find(
                conn, request_id, notification_type
            )
            if existing is not None:
                current = CitizenDeliveryStatus(existing["status"])
                if current in {
                    CitizenDeliveryStatus.SENT,
                    CitizenDeliveryStatus.DELIVERY_UNCERTAIN,
                }:
                    return CitizenNotifyResult(
                        request_id,
                        notification_type,
                        "ALREADY_SENT"
                        if current == CitizenDeliveryStatus.SENT
                        else "SKIPPED_UNCERTAIN",
                        trace_id=existing["id"],
                        provider_message_id=existing["provider_message_id"],
                    )
                trace_id = existing["id"]
            else:
                trace_id = None

            projection = CitizenCaseProjection(
                public_reference=public_reference_for(request_id),
                public_status=public_status.value,
                subject=projection_row["subject"] or "",
                public_description=projection_row["public_description"] or "",
                public_location=projection_row["public_location"],
            )
            subject, body = render_notification(notification_type, projection)
            rfc_message_id = citizen_rfc_message_id(request_id, notification_type)

            if trace_id is None:
                trace_id = await self._repository.insert_or_claim(
                    conn,
                    request_id=request_id,
                    notification_type=notification_type,
                    channel=_CHANNEL,
                    recipient=projection_row["citizen_address"],
                    public_reference=projection.public_reference,
                    subject=subject,
                    body=body,
                    dedupe_key=dedupe_key(request_id, notification_type),
                    outbound_rfc_message_id=rfc_message_id,
                )
                if trace_id is None:
                    return CitizenNotifyResult(
                        request_id, notification_type, "RACE_LOST"
                    )

            return await self._send(
                conn,
                sender=sender,
                request_id=request_id,
                notification_type=notification_type,
                trace_id=trace_id,
                recipient=projection_row["citizen_address"],
                subject=subject,
                body=body,
                rfc_message_id=rfc_message_id,
            )

    async def _send(
        self,
        conn,
        *,
        sender: RoutingMessageSenderPort,
        request_id: str,
        notification_type: CitizenNotificationType,
        trace_id: str,
        recipient: str,
        subject: str,
        body: str,
        rfc_message_id: str,
    ) -> CitizenNotifyResult:
        try:
            recovered = sender.find_sent_message_by_rfc_message_id(
                rfc_message_id
            )
            if recovered:
                observed = _safe_observed_rfc_message_id(sender, recovered)
                await self._repository.mark_sent(
                    conn,
                    trace_id,
                    provider_message_id=recovered,
                    provider_thread_id=None,
                    observed_rfc_message_id=observed,
                )
                return CitizenNotifyResult(
                    request_id,
                    notification_type,
                    "SENT_RECONCILED",
                    trace_id=trace_id,
                    provider_message_id=recovered,
                )
            external_id = sender.send_message(
                to=recipient,
                subject=subject,
                body=body,
                rfc_message_id=rfc_message_id,
            )
            observed = _safe_observed_rfc_message_id(sender, external_id)
        except Exception as exc:
            # Only provider-side failures (reconcile lookup or send) are
            # delivery failures. A persistence failure on mark_sent would have
            # already aborted this transaction and is intentionally NOT
            # classified as a delivery failure: the rollback plus the stable
            # RFC reconciliation recovers it on the next attempt without
            # duplicating the email.
            uncertain = _delivery_is_uncertain(exc)
            await self._repository.mark_failed(
                conn,
                trace_id,
                error_code=type(exc).__name__,
                error_detail=str(exc),
                uncertain=uncertain,
            )
            return CitizenNotifyResult(
                request_id,
                notification_type,
                "DELIVERY_UNCERTAIN" if uncertain else "DELIVERY_FAILED",
                trace_id=trace_id,
            )
        await self._repository.mark_sent(
            conn,
            trace_id,
            provider_message_id=external_id,
            provider_thread_id=None,
            observed_rfc_message_id=observed,
        )
        return CitizenNotifyResult(
            request_id,
            notification_type,
            "SENT",
            trace_id=trace_id,
            provider_message_id=external_id,
        )

    async def trace(self, request_id: str) -> list[dict]:
        async with transaction(self._pool) as conn:
            return await self._repository.list_traces(conn, request_id)


__all__ = [
    "CitizenNotifyResult",
    "FlowCitizenNotificationService",
    "public_state_for_notification_type",
]
