"""Gupshup WhatsApp webhook handler for Team360.

Receives Gupshup webhook payloads, validates structure, normalizes inbound
messages to InboundMessage, claims idempotency via PostgreSQL, and for new
messages connects to the existing Flow intake pipeline.

Security:
- Gupshup signature verification is not documented for this integration.
- The existing Team360 Messaging webhook token is therefore required before
  parsing, persistence, or Flow processing. A trusted sender/ingress must set
  ``x-team360-webhook-token``; missing configuration fails closed.
- PostgreSQL claiming deduplicates inbound provider message IDs before Flow.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
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
    normalize_inbound,
)
from modules.messaging.whatsapp_claim import WhatsAppMessageClaimer

logger = logging.getLogger(__name__)

# Lazy-initialized singletons (created on first request)
_claimer: WhatsAppMessageClaimer | None = None
_bridge: Any = None  # WhatsAppFlowBridge, typed as Any to avoid import cycle
_WEBHOOK_TOKEN_ENV = "TEAM360_MESSAGING_WEBHOOK_TOKEN"
_WEBHOOK_TOKEN_HEADER = "x-team360-webhook-token"
_MIN_WEBHOOK_TOKEN_LENGTH = 32


def _require_webhook_authenticity(request: Request) -> None:
    """Authenticate the sender/ingress before reading or processing the body."""
    expected = os.environ.get(_WEBHOOK_TOKEN_ENV, "").strip()
    if len(expected) < _MIN_WEBHOOK_TOKEN_LENGTH:
        raise HTTPException(status_code=503, detail="Webhook authentication unavailable")
    supplied = request.headers.get(_WEBHOOK_TOKEN_HEADER, "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid webhook credentials")


def _get_claimer() -> WhatsAppMessageClaimer:
    global _claimer
    if _claimer is None:
        pool = get_pool()
        _claimer = WhatsAppMessageClaimer(
            pool=pool,
            repository=FlowPostgresRepository(),
        )
    return _claimer


def _get_bridge():
    """Get or create the WhatsApp→Flow bridge with a real FlowIntakeService."""
    global _bridge
    if _bridge is None:
        from modules.messaging.whatsapp_flow_bridge import WhatsAppFlowBridge
        from modules.flow.service import FlowIntakeService
        from modules.flow.intake.ai import LiteLLMFlowIntakeInterpreter

        pool = get_pool()

        class _NoOpReplySender:
            """Reply sender that does nothing (WhatsApp replies deferred)."""
            sender_address = "team360@whatsapp"

            def send_reply(self, **kwargs):
                from modules.messaging.domain.messages import OutboundMessageReceipt
                return OutboundMessageReceipt(
                    external_message_id="noop",
                    external_thread_id="noop",
                )

        flow_service = FlowIntakeService(
            pool=pool,
            repository=FlowPostgresRepository(),
            interpreter=LiteLLMFlowIntakeInterpreter(),
            reply_sender=_NoOpReplySender(),
        )
        _bridge = WhatsAppFlowBridge(pool=pool, flow_service=flow_service)
    return _bridge


class GupshupWhatsAppWebhookController(Controller):
    """POST webhook endpoint for Gupshup WhatsApp events."""

    path = "/webhooks/messaging/gupshup/whatsapp"
    tags = ["Messaging Webhooks"]

    @post(status_code=200, request_max_body_size=1_048_576)
    async def receive_webhook(self, request: Request) -> dict[str, Any]:
        """Receive and process a Gupshup WhatsApp webhook event.

        Flow:
        1. Parse JSON body
        2. Identify event type (message vs status)
        3. Filter irrelevant events
        4. Claim inbound message for PostgreSQL idempotency
        5. If new, connect to Flow intake pipeline
        6. Return HTTP 200 (always, to acknowledge receipt)
        """
        _require_webhook_authenticity(request)
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
                # Step 1: Normalize
                inbound = normalize_inbound(payload)

                # Step 2: Claim for idempotency
                claimer = _get_claimer()
                claim_result = await claimer.claim(payload)

                if claim_result is None:
                    return {"ok": True, "event_type": "message", "claimed": False}

                logger.info(
                    "GUPSHUP_INBOUND_CLAIMED provider=gupshup channel=whatsapp "
                    "sender=%s message_id=%s is_new=%s conversation_id=%s",
                    claim_result.sender or "-",
                    claim_result.provider_message_id or "-",
                    claim_result.is_new,
                    claim_result.conversation_id or "-",
                )

                # Step 3: If new, connect to Flow intake
                flow_result = None
                if claim_result.is_new:
                    bridge = _get_bridge()
                    flow_result = await bridge.process(
                        inbound,
                        claim_result.conversation_id,
                        "RECEIVED",
                    )

                return {
                    "ok": True,
                    "event_type": "message",
                    "is_new": claim_result.is_new,
                    "provider_message_id": claim_result.provider_message_id,
                    "sender": claim_result.sender,
                    "conversation_id": claim_result.conversation_id,
                    "flow_processed": flow_result.processed if flow_result else False,
                    "flow_candidates": flow_result.candidate_count if flow_result else 0,
                }
            except Exception as exc:
                logger.exception(
                    "GUPSHUP_WEBHOOK_PROCESSING_FAILED event_type=%s error=%s",
                    event_type or "-",
                    exc,
                )
                return {"ok": True, "event_type": "message", "error": str(exc)}

        # --- Unknown/ignored events ---
        logger.info(
            "GUPSHUP_WEBHOOK_IGNORED event_type=%s reason=unrecognized",
            event_type or "-",
        )
        return {"ok": True, "event_type": "ignored"}


def _epoch_ms() -> int:
    return int(time.time() * 1000)
