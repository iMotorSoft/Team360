"""Gupshup WhatsApp webhook handler for Team360.

Receives Gupshup webhook payloads, validates structure, normalizes inbound
messages to InboundMessage, claims idempotency via PostgreSQL, and returns
appropriate HTTP responses.

Security:
- No signature verification in DEV (Gupshup DEV does not support it).
- Endpoint exposed only through cloudflare tunnel in DEV.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from litestar import Controller, Request, post
from litestar.exceptions import HTTPException

from modules.db.pool import get_pool
from modules.db.settings import get_database_settings
from modules.flow.repository import FlowPostgresRepository
from modules.messaging.providers.gupshup.whatsapp.mapper import (
    is_inbound_message,
    is_status_event,
)
from modules.messaging.whatsapp_claim import WhatsAppMessageClaimer

logger = logging.getLogger(__name__)

# Lazy-initialized claimer (created on first request to avoid import-time DB access)
_claimer: WhatsAppMessageClaimer | None = None


def _get_claimer() -> WhatsAppMessageClaimer:
    """Get or create the WhatsApp message claimer with a DB pool."""
    global _claimer
    if _claimer is None:
        pool = get_pool()
        _claimer = WhatsAppMessageClaimer(
            pool=pool,
            repository=FlowPostgresRepository(),
        )
    return _claimer


class GupshupWhatsAppWebhookController(Controller):
    """POST webhook endpoint for Gupshup WhatsApp events."""

    path = "/webhooks/messaging/gupshup/whatsapp"
    tags = ["Messaging Webhooks"]

    @post(status_code=200)
    async def receive_webhook(self, request: Request) -> dict[str, Any]:
        """Receive and process a Gupshup WhatsApp webhook event.

        Responsibilities:
        1. Parse JSON body
        2. Identify event type (message vs status)
        3. Filter irrelevant events
        4. Claim inbound message for PostgreSQL idempotency
        5. Return HTTP 200 (always, to acknowledge receipt)
        """
        received_at_ms = _epoch_ms()
        raw_body = await request.body()

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail="Invalid JSON"
            ) from exc

        event_type = str(payload.get("type") or "").strip().lower()
        remote_ip = request.client.host if request.client else "-"

        logger.info(
            "GUPSHUP_WEBHOOK_RECEIVED received_at_ms=%s remote_ip=%s event_type=%s",
            received_at_ms,
            remote_ip,
            event_type or "-",
        )

        # --- Status events ---
        if is_status_event(payload):
            logger.info(
                "GUPSHUP_WEBHOOK_STATUS event_type=%s reason=status_event",
                event_type or "-",
            )
            return {"ok": True, "event_type": "status"}

        # --- Inbound messages ---
        if is_inbound_message(payload):
            try:
                claimer = _get_claimer()
                result = await claimer.claim(payload)
                if result is None:
                    # Claimer returned None — payload was filtered
                    return {"ok": True, "event_type": "message", "claimed": False}

                logger.info(
                    "GUPSHUP_INBOUND_CLAIMED provider=gupshup channel=whatsapp "
                    "sender=%s message_id=%s is_new=%s conversation_id=%s",
                    result.sender or "-",
                    result.provider_message_id or "-",
                    result.is_new,
                    result.conversation_id or "-",
                )

                # TODO: CHECKPOINT 6 — if result.is_new, connect to Flow Intake
                # if result.is_new:
                #     await flow_intake.process(...)

                return {
                    "ok": True,
                    "event_type": "message",
                    "is_new": result.is_new,
                    "provider_message_id": result.provider_message_id,
                    "sender": result.sender,
                    "conversation_id": result.conversation_id,
                }
            except Exception as exc:
                logger.exception(
                    "GUPSHUP_WEBHOOK_CLAIM_FAILED event_type=%s error=%s",
                    event_type or "-",
                    exc,
                )
                # Still return 200 to avoid Gupshup retries on our internal errors
                return {"ok": True, "event_type": "message", "error": str(exc)}

        # --- Unknown/ignored events ---
        logger.info(
            "GUPSHUP_WEBHOOK_IGNORED event_type=%s reason=unrecognized",
            event_type or "-",
        )
        return {"ok": True, "event_type": "ignored"}


def _epoch_ms() -> int:
    return int(time.time() * 1000)
