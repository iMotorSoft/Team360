"""Gupshup WhatsApp inbound mapper for Team360.

Ported from Vertice360 and adapted to produce Team360 domain contracts.

Handles the following Gupshup payload variants:
- minimal: {"payload": {"from": ..., "text": ..., ...}}
- wrapper: {"type": "message", "payload": {"id": ..., "source": ..., ...}}
- nested v2: {"type": "message-event", "sender": {"phone": ...}, "payload": {...}}
- status events: {"status": {"messageId": ..., "status": ...}}
- flat: {"from": ..., "text": ..., "id": ...}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from modules.messaging.domain.messages import InboundMessage
from modules.messaging.domain.whatsapp import WHATSAPP_CHANNEL

logger = logging.getLogger(__name__)

STATUS_LIKE_VALUES = {
    "accepted",
    "queued",
    "enqueued",
    "submitted",
    "sent",
    "delivered",
    "read",
    "failed",
    "fail",
    "error",
    "undelivered",
}

NON_STATUS_TYPES = {
    "message",
    "text",
    "image",
    "video",
    "audio",
    "file",
    "document",
    "location",
    "contacts",
    "interactive",
    "button",
    "reaction",
    "sticker",
}


def normalize_inbound(payload: Mapping[str, Any]) -> InboundMessage:
    """Normalize a Gupshup WhatsApp payload into an InboundMessage.

    Implements WhatsAppInboundNormalizer protocol.

    Raises ValueError if the payload contains no recognizable message.
    """
    parsed_list = _parse_inbound(dict(payload))
    if not parsed_list:
        raise ValueError("No inbound message found in Gupshup payload")

    parsed = parsed_list[0]
    received_at = _parse_timestamp(parsed.timestamp)

    return InboundMessage(
        provider="gupshup",
        channel=WHATSAPP_CHANNEL,
        external_message_id=parsed.message_id or "",
        external_thread_id=parsed.message_id or "",
        sender=parsed.from_ or "",
        recipients=(parsed.to,) if parsed.to else (),
        subject="",
        text_body=parsed.text or "",
        received_at=received_at,
        metadata={
            "wa_id": parsed.wa_id or "",
            "raw": parsed.raw,
        },
    )


def is_status_event(payload: Mapping[str, Any]) -> bool:
    """Check if a payload is a delivery status event (not an inbound message)."""
    return len(_parse_status(dict(payload))) > 0


def is_inbound_message(payload: Mapping[str, Any]) -> bool:
    """Check if a payload is an inbound message (not a status event)."""
    return len(_parse_inbound(dict(payload))) > 0 and not is_status_event(payload)


# ---------------------------------------------------------------------------
# Internal parsing (ported from V360 mapper.py)
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class _NormalizedInbound:
    provider: str
    service: str
    wa_id: str | None
    from_: str | None
    to: str | None
    text: str | None
    timestamp: str | int | None
    message_id: str | None
    raw: dict[str, Any]


def _parse_inbound(payload: dict[str, Any]) -> list[_NormalizedInbound]:
    messages = _collect_messages(payload)
    if not messages and _looks_like_message(payload):
        messages = [payload]

    results: list[_NormalizedInbound] = []
    for message in messages:
        payload_l1 = (
            message.get("payload")
            if isinstance(message.get("payload"), dict)
            else {}
        )
        payload_l2 = (
            payload_l1.get("payload")
            if isinstance(payload_l1.get("payload"), dict)
            else {}
        )
        wa_id = _first_non_empty(
            message.get("wa_id"),
            message.get("from"),
            message.get("sender"),
            message.get("source"),
            payload_l1.get("wa_id"),
            payload_l1.get("from"),
            payload_l1.get("sender"),
            payload_l1.get("source"),
        )
        from_candidate = _first_non_empty(
            message.get("from"),
            message.get("sender"),
            message.get("source"),
            payload_l1.get("from"),
            payload_l1.get("sender"),
            payload_l1.get("source"),
            wa_id,
        )
        if isinstance(from_candidate, dict):
            from_ = str(
                from_candidate.get("phone")
                or from_candidate.get("from")
                or ""
            )
        else:
            from_ = from_candidate
        to = _first_non_empty(
            message.get("to"),
            message.get("destination"),
            message.get("dest"),
            message.get("recipient"),
            payload_l1.get("to"),
            payload_l1.get("destination"),
            payload_l1.get("dest"),
            payload_l1.get("recipient"),
        )
        text = _extract_text(message)
        timestamp = _first_non_empty(
            message.get("timestamp"),
            message.get("time"),
            message.get("ts"),
            payload_l1.get("timestamp"),
            payload_l1.get("time"),
            payload_l1.get("ts"),
        )
        message_id = _first_non_empty(
            message.get("message_id"),
            message.get("messageId"),
            message.get("id"),
            message.get("mid"),
            payload_l1.get("message_id"),
            payload_l1.get("messageId"),
            payload_l1.get("id"),
            payload_l1.get("mid"),
            payload_l2.get("message_id"),
            payload_l2.get("messageId"),
            payload_l2.get("id"),
            payload_l2.get("mid"),
        )
        results.append(
            _NormalizedInbound(
                provider="gupshup",
                service="whatsapp",
                wa_id=_as_str(wa_id),
                from_=_as_str(from_),
                to=_as_str(to),
                text=_as_str(text),
                timestamp=timestamp,
                message_id=_as_str(message_id),
                raw=message,
            )
        )
    return results


def _parse_status(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract status information from a Gupshup payload."""
    statuses = _collect_statuses(payload)
    if not statuses and _looks_like_status(payload):
        statuses = [payload]

    results: list[dict[str, Any]] = []
    for status in statuses:
        status_payload = (
            status.get("payload")
            if isinstance(status.get("payload"), dict)
            else {}
        )
        message_id = _first_non_empty(
            status.get("gsId"),
            status.get("message_id"),
            status.get("messageId"),
            status.get("id"),
            status.get("mid"),
            status_payload.get("gsId"),
            status_payload.get("message_id"),
            status_payload.get("messageId"),
            status_payload.get("id"),
            status_payload.get("whatsappMessageId"),
        )
        raw_status = _first_non_empty(
            status.get("status"),
            status.get("state"),
            status.get("event"),
            status.get("type"),
            status_payload.get("status"),
            status_payload.get("state"),
            status_payload.get("event"),
            status_payload.get("type"),
        )
        normalized = _normalize_status(_as_str(raw_status))
        if normalized == "message-event":
            continue
        timestamp = _first_non_empty(
            status.get("timestamp"),
            status.get("time"),
            status.get("ts"),
            status_payload.get("timestamp"),
            status_payload.get("time"),
            status_payload.get("ts"),
        )
        results.append(
            {
                "provider": "gupshup",
                "service": "whatsapp",
                "message_id": _as_str(message_id),
                "status": normalized,
                "timestamp": timestamp,
                "raw": status,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------

def _collect_messages(payload: Any) -> list[dict[str, Any]]:
    return _collect_items(
        payload,
        item_key="messages",
        single_key="message",
        looks_like=_looks_like_message,
    )


def _collect_statuses(payload: Any) -> list[dict[str, Any]]:
    return _collect_items(
        payload,
        item_key="statuses",
        single_key="status",
        looks_like=_looks_like_status,
    )


def _collect_items(
    payload: Any,
    *,
    item_key: str,
    single_key: str,
    looks_like: Any = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[int] = set()

    def _append(item: dict[str, Any]) -> None:
        item_id = id(item)
        if item_id in seen:
            return
        seen.add(item_id)
        items.append(item)

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        if item_key in node and isinstance(node[item_key], list):
            for item in node[item_key]:
                if isinstance(item, dict):
                    _append(item)
        if single_key in node and isinstance(node[single_key], dict):
            _append(node[single_key])
        if "payload" in node:
            _walk(node.get("payload"))
        if "data" in node and isinstance(node["data"], list):
            for item in node["data"]:
                _walk(item)
        if looks_like is not None and looks_like(node):
            _append(node)

    _walk(payload)
    return items


def _looks_like_message(payload: dict[str, Any]) -> bool:
    if _looks_like_status(payload):
        return False
    has_sender = any(
        key in payload for key in ("from", "sender", "source", "wa_id")
    )
    has_content = any(key in payload for key in ("text", "message"))
    if not has_content and "payload" in payload and isinstance(
        payload["payload"], dict
    ):
        inner = payload["payload"]
        has_content = any(key in inner for key in ("text", "body", "caption"))
        if (
            not has_content
            and "payload" in inner
            and isinstance(inner["payload"], dict)
        ):
            inner_2 = inner["payload"]
            has_content = any(
                key in inner_2 for key in ("text", "body", "caption")
            )
    has_destination = any(
        key in payload for key in ("to", "destination", "dest", "recipient")
    )
    return (has_sender and (has_content or has_destination)) or (
        has_content and has_destination
    )


def _looks_like_status(payload: dict[str, Any]) -> bool:
    status_candidate = _first_non_empty(
        payload.get("status"),
        payload.get("state"),
        payload.get("event"),
        payload.get("type"),
    )
    has_status_field = status_candidate is not None and not isinstance(
        status_candidate, dict
    )
    has_explicit_status = any(
        key in payload for key in ("status", "state", "event")
    )
    has_message_id = any(
        key in payload for key in ("message_id", "messageId", "mid")
    )
    has_gs_id = "gsId" in payload
    status_text = (_as_str(status_candidate) or "").strip().lower()
    if not has_status_field:
        return False
    if status_text in NON_STATUS_TYPES:
        return False
    if status_text == "message-event":
        if _looks_like_message_event_wrapper(payload):
            return False
        return True
    if has_explicit_status:
        return True
    if status_text and status_text in STATUS_LIKE_VALUES:
        return True
    if has_message_id or has_gs_id:
        return True
    status_value = payload.get("status")
    if isinstance(status_value, dict):
        return False
    return True


def _looks_like_message_event_wrapper(payload: dict[str, Any]) -> bool:
    """Detect message-event wrappers that actually carry inbound content."""
    candidates: list[dict[str, Any]] = []
    current: Any = payload
    for _ in range(3):
        if not isinstance(current, dict):
            break
        candidates.append(current)
        current = current.get("payload")

    has_sender = any(
        _first_non_empty(
            node.get("from"),
            node.get("sender"),
            node.get("source"),
            node.get("wa_id"),
        )
        is not None
        for node in candidates
    )
    has_destination = any(
        _first_non_empty(
            node.get("to"),
            node.get("destination"),
            node.get("dest"),
            node.get("recipient"),
        )
        is not None
        for node in candidates
    )
    has_text_like = any(_extract_text(node) is not None for node in candidates)
    has_non_status_type = any(
        (
            _as_str(
                _first_non_empty(
                    node.get("type"),
                    node.get("event"),
                    node.get("status"),
                    node.get("state"),
                )
            )
            or ""
        ).strip().lower()
        in NON_STATUS_TYPES
        for node in candidates
    )
    return (has_sender and has_text_like) or (
        has_non_status_type
        and (has_sender or has_destination or has_text_like)
    )


def _extract_text(message: dict[str, Any]) -> str | None:
    text = message.get("text")
    if isinstance(text, dict):
        return _as_str(text.get("body") or text.get("text"))
    if isinstance(text, str):
        return text
    payload = message.get("payload")
    if isinstance(payload, dict):
        payload_text = payload.get("text")
        if isinstance(payload_text, str):
            return payload_text
        if isinstance(payload_text, dict):
            return _as_str(
                payload_text.get("body") or payload_text.get("text")
            )
        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            nested_text = nested_payload.get("text")
            if isinstance(nested_text, str):
                return nested_text
            if isinstance(nested_text, dict):
                return _as_str(
                    nested_text.get("body") or nested_text.get("text")
                )
            return _as_str(
                nested_payload.get("body") or nested_payload.get("caption")
            )
        return _as_str(payload.get("body") or payload.get("caption"))
    return _as_str(message.get("message"))


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_status(status: str | None) -> str | None:
    if not status:
        return None
    cleaned = status.strip().lower()
    known = {
        "accepted": "queued",
        "queued": "queued",
        "enqueued": "queued",
        "submitted": "queued",
        "sent": "sent",
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
        "fail": "failed",
        "error": "failed",
    }
    return known.get(cleaned, cleaned)


def _parse_timestamp(value: str | int | None) -> datetime:
    """Parse Gupshup timestamp to UTC datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    try:
        ts = int(str(value).strip())
        # Gupshup timestamps can be seconds or milliseconds
        if ts > 1e12:
            ts = ts // 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, OSError):
        return datetime.now(timezone.utc)
