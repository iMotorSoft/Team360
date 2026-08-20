"""Flow email intake use case with human confirmation and idempotency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import fetch_one, transaction
from modules.messaging.domain import InboundMessage, OutboundMessageReceipt

from .domain.models import CandidateRequest
from .domain.states import ConversationState, transition
from .intake.ai import FlowIntakeInterpreterPort
from .repository import FlowPostgresRepository


class FlowReplySenderPort(Protocol):
    sender_address: str

    def send_reply(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        in_reply_to: str = "",
        references: str = "",
    ) -> OutboundMessageReceipt: ...


@dataclass(frozen=True, slots=True)
class ProcessResult:
    processed: bool
    conversation_id: str | None
    state: ConversationState | None
    candidate_count: int = 0
    confirmed_count: int = 0
    outbound_message_id: str | None = None


def confirmation_text(requests: tuple[CandidateRequest, ...]) -> str:
    if len(requests) == 1:
        request = requests[0]
        location = f" en {request.location_text}" if request.location_text else ""
        return f"Entendí que querés solicitar: {request.description}{location}. ¿Es correcto?"
    lines = ["Entendí estas solicitudes:", ""]
    for ordinal, request in enumerate(requests, start=1):
        location = f" — {request.location_text}" if request.location_text else ""
        lines.append(f"{ordinal}. {request.description}{location}")
    lines.extend(["", "¿Son correctas?"])
    return "\n".join(lines)


class FlowIntakeService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowPostgresRepository,
        interpreter: FlowIntakeInterpreterPort,
        reply_sender: FlowReplySenderPort,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._interpreter = interpreter
        self._reply_sender = reply_sender

    async def process(self, message: InboundMessage) -> ProcessResult:
        async with transaction(self._pool) as conn:
            claimed = await self._repository.claim_inbound(conn, message)
            if not claimed.is_new:
                return ProcessResult(False, claimed.conversation_id, claimed.state)
            return await self._process_from_claimed(conn, claimed, message)

    async def process_whatsapp(
        self, message: InboundMessage, conversation_id: str, state: str
    ) -> ProcessResult:
        """Process a WhatsApp message already claimed by the webhook.

        The webhook already created the conversation and message via
        claim_whatsapp_inbound(). This method runs the Flow intake
        logic (interpretation, candidates) without re-claiming.
        """
        async with transaction(self._pool) as conn:
            row = await fetch_one(
                conn,
                """
                SELECT c.id::text, c.state, c.candidate_revision,
                       m.id::text as message_id
                FROM flow_conversations c
                LEFT JOIN flow_messages m ON m.conversation_id = c.id
                    AND m.direction = 'inbound'
                WHERE c.id = %(id)s
                ORDER BY m.created_at_utc DESC
                LIMIT 1
                """,
                {"id": conversation_id},
            )
            if row is None:
                return ProcessResult(
                    False, conversation_id, ConversationState(state)
                )

            @dataclass(frozen=True, slots=True)
            class _Claimed:
                is_new: bool
                message_id: str | None
                conversation_id: str
                state: ConversationState
                revision: int

            claimed = _Claimed(
                is_new=True,
                message_id=row.get("message_id"),
                conversation_id=row["id"],
                state=ConversationState(row["state"]),
                revision=int(row["candidate_revision"]),
            )
            return await self._process_from_claimed(conn, claimed, message)

    async def _process_from_claimed(
        self, conn, claimed, message: InboundMessage
    ) -> ProcessResult:
        """Shared processing logic for both email and WhatsApp intake."""
        if claimed.state == ConversationState.RECEIVED:
            return await self._process_initial(conn, claimed, message)
        if claimed.state in {
            ConversationState.PENDING_CONFIRMATION,
            ConversationState.PENDING_CLARIFICATION,
            ConversationState.CORRECTED,
            ConversationState.INTERPRETED,
        }:
            return await self._process_reply(conn, claimed, message)
        return ProcessResult(True, claimed.conversation_id, claimed.state)

    async def _process_initial(self, conn, claimed, message: InboundMessage) -> ProcessResult:
        interpretation = self._interpreter.interpret_initial(message)
        await self._repository.add_interpretation(
            conn,
            conversation_id=claimed.conversation_id,
            source_message_id=claimed.message_id,
            phase="initial",
            outcome="requests" if interpretation.requests else "clarification",
            payload={
                "requests": [item.as_dict() for item in interpretation.requests],
                "clarification_question": interpretation.clarification_question,
            },
            provider=interpretation.provider,
            model=interpretation.model,
            usage=interpretation.usage,
            latency_ms=interpretation.latency_ms,
        )
        if not interpretation.requests:
            state = transition(ConversationState.RECEIVED, ConversationState.PENDING_CLARIFICATION)
            body = interpretation.clarification_question or (
                "No llegué a identificar la solicitud. ¿Podés contarme qué pasó y dónde?"
            )
            outbound = await self._send_and_record(conn, claimed.conversation_id, message, body)
            await self._repository.update_state(conn, claimed.conversation_id, state)
            return ProcessResult(
                True,
                claimed.conversation_id,
                state,
                outbound_message_id=outbound.external_message_id,
            )

        await self._repository.replace_candidates(
            conn,
            conversation_id=claimed.conversation_id,
            revision=claimed.revision,
            requests=interpretation.requests,
        )
        interpreted = transition(ConversationState.RECEIVED, ConversationState.INTERPRETED)
        await self._repository.update_state(conn, claimed.conversation_id, interpreted)
        state = transition(interpreted, ConversationState.PENDING_CONFIRMATION)
        outbound = await self._send_and_record(
            conn, claimed.conversation_id, message, confirmation_text(interpretation.requests)
        )
        await self._repository.update_state(conn, claimed.conversation_id, state)
        return ProcessResult(
            True,
            claimed.conversation_id,
            state,
            candidate_count=len(interpretation.requests),
            outbound_message_id=outbound.external_message_id,
        )

    async def _process_reply(self, conn, claimed, message: InboundMessage) -> ProcessResult:
        stored = await self._repository.active_candidates(conn, claimed.conversation_id)
        current = tuple(item.request for item in stored)
        interpretation = self._interpreter.interpret_reply(message, current)
        await self._repository.add_interpretation(
            conn,
            conversation_id=claimed.conversation_id,
            source_message_id=claimed.message_id,
            phase="reply",
            outcome=interpretation.action,
            payload={
                "requests": [item.as_dict() for item in interpretation.requests],
                "clarification_question": interpretation.clarification_question,
            },
            provider=interpretation.provider,
            model=interpretation.model,
            usage=interpretation.usage,
            latency_ms=interpretation.latency_ms,
        )
        if interpretation.action == "confirm_all":
            can_confirm = claimed.state in {
                ConversationState.PENDING_CONFIRMATION,
                ConversationState.PENDING_CLARIFICATION,
            } and bool(current)
            if can_confirm:
                state = transition(claimed.state, ConversationState.CONFIRMED)
                confirmed = await self._repository.confirm_active_candidates(
                    conn, claimed.conversation_id
                )
                await self._repository.update_state(conn, claimed.conversation_id, state)
                return ProcessResult(
                    True, claimed.conversation_id, state, len(current), confirmed
                )

        if interpretation.action in {"correction", "reinterpret"}:
            if claimed.state == ConversationState.PENDING_CONFIRMATION:
                corrected = transition(claimed.state, ConversationState.CORRECTED)
            elif claimed.state == ConversationState.PENDING_CLARIFICATION:
                corrected = transition(claimed.state, ConversationState.CORRECTED)
            else:
                corrected = ConversationState.CORRECTED
            await self._repository.update_state(conn, claimed.conversation_id, corrected)
            await self._repository.replace_candidates(
                conn,
                conversation_id=claimed.conversation_id,
                revision=claimed.revision,
                requests=interpretation.requests,
            )
            interpreted = transition(corrected, ConversationState.INTERPRETED)
            await self._repository.update_state(conn, claimed.conversation_id, interpreted)
            pending = transition(interpreted, ConversationState.PENDING_CONFIRMATION)
            outbound = await self._send_and_record(
                conn,
                claimed.conversation_id,
                message,
                confirmation_text(interpretation.requests),
            )
            await self._repository.update_state(conn, claimed.conversation_id, pending)
            return ProcessResult(
                True,
                claimed.conversation_id,
                pending,
                len(interpretation.requests),
                outbound_message_id=outbound.external_message_id,
            )

        body = interpretation.clarification_question or (
            "No pude confirmar si las solicitudes están correctas. "
            "¿Podés responder sí o indicar qué habría que corregir?"
        )
        if claimed.state == ConversationState.PENDING_CONFIRMATION:
            state = transition(claimed.state, ConversationState.PENDING_CLARIFICATION)
        else:
            state = ConversationState.PENDING_CLARIFICATION
        outbound = await self._send_and_record(conn, claimed.conversation_id, message, body)
        await self._repository.update_state(conn, claimed.conversation_id, state)
        return ProcessResult(
            True,
            claimed.conversation_id,
            state,
            len(current),
            outbound_message_id=outbound.external_message_id,
        )

    async def _send_and_record(
        self, conn, conversation_id: str, message: InboundMessage, body: str
    ) -> OutboundMessageReceipt:
        outbound = self._reply_sender.send_reply(
            to=message.sender,
            subject=message.subject,
            body=body,
            thread_id=message.external_thread_id,
            in_reply_to=str(message.metadata.get("rfc_message_id") or ""),
            references=str(message.metadata.get("references") or ""),
        )
        await self._repository.record_outbound(
            conn,
            conversation_id=conversation_id,
            external_message_id=outbound.external_message_id,
            sender=self._reply_sender.sender_address,
            recipient=message.sender,
            subject=message.subject,
            body=body,
            external_thread_id=outbound.external_thread_id,
        )
        return outbound
