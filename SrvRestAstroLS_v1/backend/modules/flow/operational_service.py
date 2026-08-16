"""Correlate and process routing-scoped operational replies before intake."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction
from modules.messaging.domain import InboundMessage

from .closure_service import ClosureProposalResult, FlowClosureService
from .domain import (
    CorrelatedOperationalReply,
    OperationalAction,
    OperationalRoutingContext,
    OperationalStatus,
    request_id_from_subject,
    rfc_reference_ids,
    routing_key_from_subject,
)
from .operational_ai import OperationalInterpreterPort
from .operational_repository import FlowOperationalPostgresRepository


@dataclass(frozen=True, slots=True)
class OperationalProcessResult:
    matched: bool
    processed: bool
    request_id: str | None = None
    routing_id: str | None = None
    level: int | None = None
    event_id: str | None = None
    action: OperationalAction | None = None
    status: OperationalStatus | None = None
    first_response_at: datetime | None = None
    correlation_method: str | None = None
    proposal: ClosureProposalResult | None = None


class FlowOperationalReplyService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowOperationalPostgresRepository,
        interpreter: OperationalInterpreterPort,
        closure: FlowClosureService | None = None,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._interpreter = interpreter
        self._closure = closure

    async def process_if_operational(
        self, message: InboundMessage
    ) -> OperationalProcessResult:
        async with transaction(self._pool) as conn:
            correlation = await self._correlate(conn, message)
            if correlation is None:
                return OperationalProcessResult(False, False)

            context = correlation.context
            if context.request_status == "RESOLVED":
                return OperationalProcessResult(
                    matched=True,
                    processed=False,
                    request_id=context.request_id,
                    routing_id=context.routing_id,
                    level=context.level,
                    correlation_method=correlation.method,
                )

            source_message_id = await self._repository.claim_message(
                conn, context=context, message=message
            )
            if source_message_id is None:
                event = await self._repository.event_for_message(
                    conn, message.provider, message.external_message_id
                )
                return OperationalProcessResult(
                    matched=True,
                    processed=False,
                    request_id=context.request_id,
                    routing_id=context.routing_id,
                    level=context.level,
                    event_id=event["event_id"] if event else None,
                    action=(
                        OperationalAction(event["interpretation_action"])
                        if event else None
                    ),
                    correlation_method=(event["correlation_method"] if event else None),
                )

            state = await self._repository.ensure_work_state(conn, context)
            interpretation = self._interpreter.interpret(message)
            event_id = await self._repository.record_event(
                conn,
                context=context,
                source_message_id=source_message_id,
                message=message,
                correlation_method=correlation.method,
                interpretation=interpretation,
            )
            if interpretation.action in {
                OperationalAction.ACK_OR_PROGRESS,
                OperationalAction.RESOLUTION_PROPOSED,
            }:
                state = await self._repository.mark_in_progress(
                    conn, context=context, message=message
                )

            proposal = None
            if (
                interpretation.action == OperationalAction.RESOLUTION_PROPOSED
                and self._closure is not None
            ):
                proposal = await self._closure.propose_resolution(
                    conn,
                    context=context,
                    message=message,
                    interpretation=interpretation,
                )

            return OperationalProcessResult(
                matched=True,
                processed=True,
                request_id=context.request_id,
                routing_id=context.routing_id,
                level=context.level,
                event_id=event_id,
                action=interpretation.action,
                status=state.status,
                first_response_at=state.first_response_at,
                correlation_method=correlation.method,
                proposal=proposal,
            )

    async def _correlate(
        self, conn: AsyncConnection, message: InboundMessage
    ) -> CorrelatedOperationalReply | None:
        in_reply_to = str(message.metadata.get("in_reply_to") or "").strip()
        if in_reply_to:
            context = await self._repository.find_by_rfc_reference(
                conn, rfc_reference_ids(in_reply_to, "")
            )
            if context is not None:
                return self._reply_correlation(
                    context, message, "in_reply_to_rfc"
                )

        references = str(message.metadata.get("references") or "").strip()
        if references:
            context = await self._repository.find_by_rfc_reference(
                conn, rfc_reference_ids("", references)
            )
            if context is not None:
                return self._reply_correlation(
                    context, message, "references_rfc"
                )

        request_id = request_id_from_subject(message.subject)
        if request_id:
            routing_key = routing_key_from_subject(message.subject)
            if routing_key:
                context = await self._repository.find_by_request_routing_key(
                    conn,
                    request_id=request_id,
                    routing_key=routing_key,
                )
                if context is not None:
                    return self._reply_correlation(
                        context, message, "subject_routing_token"
                    )
                return None

            context = await self._repository.find_unambiguous_by_request_id(
                conn, request_id
            )
            if context is not None:
                return self._reply_correlation(
                    context, message, "subject_request_token"
                )
        return None

    @staticmethod
    def _reply_correlation(
        context: OperationalRoutingContext,
        message: InboundMessage,
        method: str,
    ) -> CorrelatedOperationalReply | None:
        recipients = {value.casefold() for value in message.recipients}
        if context.destination.casefold() in recipients:
            return None
        return CorrelatedOperationalReply(context, method)
