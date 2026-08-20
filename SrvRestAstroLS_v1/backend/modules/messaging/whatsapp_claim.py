"""WhatsApp inbound message claiming service.

Wraps the existing Flow repository idempotency mechanism for WhatsApp
webhook use. Does NOT start Flow classification/intake — that is
deferred to the next checkpoint.

The service is intentionally minimal:
- Claim the message (atomic idempotency via PostgreSQL)
- Return whether it is new or duplicate
- No AI, no classification, no email, no outbound replies
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modules.db.transaction import transaction
from modules.messaging.domain.messages import InboundMessage
from modules.messaging.providers.gupshup.whatsapp.mapper import (
    is_inbound_message,
    is_status_event,
    normalize_inbound,
)


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """Result of a WhatsApp inbound message claim attempt."""

    is_new: bool
    provider_message_id: str
    sender: str
    conversation_id: str
    message_id: str | None


class WhatsAppClaimRepository(Protocol):
    """Protocol for the repository that claims WhatsApp inbound messages."""

    async def claim_whatsapp_inbound(
        self, conn, message: InboundMessage
    ) -> dict:
        """Claim a WhatsApp inbound message. Returns row with is_new flag."""
        ...


class WhatsAppMessageClaimer:
    """Claims WhatsApp inbound messages with PostgreSQL idempotency.

    Usage:
        claimer = WhatsAppMessageClaimer(pool=pool, repository=repo)
        result = await claimer.claim(payload)
        if result.is_new:
            # process downstream
        else:
            # duplicate, skip
    """

    def __init__(self, pool, repository) -> None:
        self._pool = pool
        self._repository = repository

    async def claim(self, payload: dict) -> ClaimResult | None:
        """Parse a Gupshup payload and claim it for idempotency.

        Returns ClaimResult if the payload is a valid inbound message.
        Returns None if the payload is a status event or unparseable.
        """
        if is_status_event(payload):
            return None
        if not is_inbound_message(payload):
            return None

        inbound = normalize_inbound(payload)
        async with transaction(self._pool) as conn:
            claimed = await self._repository.claim_whatsapp_inbound(conn, inbound)
        return ClaimResult(
            is_new=claimed["is_new"],
            provider_message_id=inbound.external_message_id,
            sender=inbound.sender,
            conversation_id=claimed["conversation_id"],
            message_id=claimed.get("message_id"),
        )
