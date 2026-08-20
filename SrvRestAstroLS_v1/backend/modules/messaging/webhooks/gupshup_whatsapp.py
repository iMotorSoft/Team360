"""Gupshup WhatsApp webhook handler for Team360.

Receives Gupshup webhook payloads, validates structure, normalizes inbound
messages to InboundMessage, and returns appropriate HTTP responses.

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
from litestar.response import Response

from modules.messaging.domain.messages import InboundMessage
from modules.messaging.providers.gupshup.whatsapp.mapper import (
    is_inbound_message,
    is_status_event,
    normalize_inbound,
)

logger = logging.getLogger(__name__)


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
        4. Normalize inbound messages via mapper
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
                inbound = normalize_inbound(payload)
                logger.info(
                    "GUPSHUP_INBOUND_NORMALIZED provider=%s channel=%s sender=%s "
                    "message_id=%s text_len=%d",
                    inbound.provider,
                    inbound.channel,
                    inbound.sender or "-",
                    inbound.external_message_id or "-",
                    len(inbound.text_body or ""),
                )
                # TODO: CHECKPOINT 6 — delegate to Flow Intake
                # flow_intake.process(inbound)
                return {
                    "ok": True,
                    "event_type": "message",
                    "message_id": inbound.external_message_id,
                    "sender": inbound.sender,
                }
            except ValueError as exc:
                logger.warning(
                    "GUPSHUP_WEBHOOK_NORMALIZE_FAILED event_type=%s error=%s",
                    event_type or "-",
                    exc,
                )
                return {"ok": True, "event_type": "message", "normalized": False}

        # --- Unknown/ignored events ---
        logger.info(
            "GUPSHUP_WEBHOOK_IGNORED event_type=%s reason=unrecognized",
            event_type or "-",
        )
        return {"ok": True, "event_type": "ignored"}


def _epoch_ms() -> int:
    return int(time.time() * 1000)
