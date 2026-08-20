"""WhatsApp → Flow Intake bridge.

Minimal integration that connects WhatsApp inbound messages to the existing
Flow classification and intake pipeline. Does NOT modify Flow domain logic.

The bridge:
1. Claims the message (idempotency, already done by webhook)
2. Passes InboundMessage to FlowIntakeService.process()
3. Returns the result

Flow classification, candidate creation, and routing work unchanged.
Email confirmation is replaced by WhatsApp acknowledgment (future gate).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from modules.db.transaction import transaction
from modules.messaging.domain.messages import InboundMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WhatsAppFlowResult:
    """Result of processing a WhatsApp message through Flow intake."""

    processed: bool
    is_new: bool
    conversation_id: str | None
    candidate_count: int = 0
    confirmed_count: int = 0


class FlowIntakeServicePort(Protocol):
    """Protocol for the Flow intake service."""

    async def process(self, message: InboundMessage): ...


class WhatsAppFlowBridge:
    """Connects WhatsApp inbound to Flow intake.

    Usage:
        bridge = WhatsAppFlowBridge(pool=pool, flow_service=flow_service)
        result = await bridge.process(inbound_message)
    """

    def __init__(self, pool, flow_service: FlowIntakeServicePort) -> None:
        self._pool = pool
        self._flow_service = flow_service

    async def process(self, message: InboundMessage, conversation_id: str, state: str) -> WhatsAppFlowResult:
        """Process a WhatsApp inbound message through Flow intake.

        The webhook already claimed the message and created the conversation.
        This method runs Flow interpretation and candidate creation.
        """
        try:
            result = await self._flow_service.process_whatsapp(
                message, conversation_id, state
            )
            logger.info(
                "WHATSAPP_FLOW_PROCESSED provider=%s channel=%s sender=%s "
                "message_id=%s processed=%s conversation_id=%s "
                "candidates=%s confirmed=%s",
                message.provider,
                message.channel,
                message.sender or "-",
                message.external_message_id or "-",
                result.processed,
                result.conversation_id or "-",
                result.candidate_count,
                result.confirmed_count,
            )
            return WhatsAppFlowResult(
                processed=result.processed,
                is_new=result.processed,
                conversation_id=result.conversation_id,
                candidate_count=result.candidate_count,
                confirmed_count=result.confirmed_count,
            )
        except Exception as exc:
            logger.exception(
                "WHATSAPP_FLOW_FAILED provider=%s sender=%s message_id=%s error=%s",
                message.provider,
                message.sender or "-",
                message.external_message_id or "-",
                exc,
            )
            return WhatsAppFlowResult(
                processed=False,
                is_new=False,
                conversation_id=None,
            )
