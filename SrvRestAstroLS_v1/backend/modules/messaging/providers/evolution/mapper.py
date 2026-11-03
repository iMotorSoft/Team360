"""Normalize only plain text and delivery; discard raw payloads and secrets."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any

from modules.messaging.domain.delivery import DeliveryEvent
from modules.messaging.domain.messages import InboundMessage

_STATUSES = {"SENT": "sent", "SERVER_ACK": "sent", "DELIVERED": "delivered",
             "DELIVERY_ACK": "delivered", "READ": "read", "READ_ACK": "read",
             "FAILED": "failed", "ERROR": "failed"}


def normalize_events(payload: Any, *, instance: str, recipient: str,
                     received_at: datetime) -> tuple[InboundMessage | DeliveryEvent, ...]:
    if not isinstance(payload, dict) or payload.get("instance") != instance:
        return ()
    kind = payload.get("event")
    if kind not in {"messages.upsert", "messages.update"}:
        return ()
    data = payload.get("data")
    records = data if isinstance(data, list) else [data]
    events = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if kind == "messages.update":
            # Meta v2.3.7 uses keyId, not the Prisma messageId; fromMe is
            # incorrectly false on Meta statuses, so don't filter on that flag.
            key = record.get("key")
            key = key if isinstance(key, dict) else {}
            message_id = record.get("keyId") or key.get("id")
            status = _STATUSES.get(str(record.get("status", "")).upper())
            if isinstance(message_id, str) and message_id and status:
                events.append(DeliveryEvent("evolution", instance, message_id, status, received_at))
            continue
        key, message = record.get("key"), record.get("message")
        if not isinstance(key, dict) or not isinstance(message, dict) or key.get("fromMe") is not False:
            continue
        message_id, jid = key.get("id"), key.get("remoteJid")
        if (not isinstance(message_id, str) or not message_id or not isinstance(jid, str)
                or not re.fullmatch(r"[1-9][0-9]{6,14}@s\.whatsapp\.net", jid)):
            continue
        text = message.get("conversation")
        if text is None:
            extended = message.get("extendedTextMessage")
            text = extended.get("text") if isinstance(extended, dict) else None
        if not isinstance(text, str) or not text or len(text) > 4096:
            continue
        # Transport timestamp is optional; receipt time is always authoritative.
        metadata = {"provider_instance": instance,
                    "raw_event_reference": hashlib.sha256(f"{instance}:{message_id}".encode()).hexdigest()}
        timestamp = record.get("messageTimestamp")
        try:
            if not isinstance(timestamp, bool) and timestamp is not None:
                metadata["provider_timestamp"] = datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            pass
        sender = jid.split("@")[0]
        events.append(InboundMessage(
            provider="evolution", channel="whatsapp", external_message_id=message_id,
            external_thread_id=sender, sender=sender, recipients=(recipient,),
            subject="", text_body=text, received_at=received_at, metadata=metadata,
        ))
    return tuple(events)
