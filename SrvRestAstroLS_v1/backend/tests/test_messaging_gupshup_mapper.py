"""Gupshup WhatsApp inbound mapper tests.

Ported from Vertice360 test_gupshup_whatsapp_mapper.py and adapted for
Team360 domain contracts. Tests all recognized Gupshup payload variants.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure backend root is on sys.path for module imports
_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from modules.messaging.providers.gupshup.whatsapp.mapper import (  # noqa: E402
    normalize_inbound,
    is_status_event,
    is_inbound_message,
    _parse_inbound,
    _parse_status,
)


# ---------------------------------------------------------------------------
# Inbound parsing tests (ported from V360)
# ---------------------------------------------------------------------------


def test_parse_inbound_minimal_payload() -> None:
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "hola",
            "timestamp": "1700000000",
            "id": "msg-123",
        }
    }
    messages = _parse_inbound(payload)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.provider == "gupshup"
    assert msg.service == "whatsapp"
    assert msg.wa_id == "5491122334455"
    assert msg.from_ == "5491122334455"
    assert msg.to == "14155551234"
    assert msg.text == "hola"
    assert msg.timestamp == "1700000000"
    assert msg.message_id == "msg-123"


def test_parse_inbound_wrapper_payload() -> None:
    payload = {
        "app": "team360dev",
        "timestamp": 1770565000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "inbound-msg-001",
            "source": "541130946950",
            "destination": "5491100000000",
            "type": "text",
            "payload": {"text": "OK DobleVia"},
        },
    }
    messages = _parse_inbound(payload)
    statuses = _parse_status(payload)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.from_ == "541130946950"
    assert msg.to == "5491100000000"
    assert msg.message_id == "inbound-msg-001"
    assert msg.text == "OK DobleVia"
    assert statuses == []


def test_parse_inbound_message_event_wrapper_live_payload() -> None:
    payload = {
        "app": "team360dev",
        "timestamp": 1770565000000,
        "version": 2,
        "type": "message-event",
        "sender": {"phone": "541130946950"},
        "destination": "5491100000000",
        "payload": {
            "id": "inbound-msg-002",
            "type": "text",
            "payload": {"text": "Hola live"},
        },
    }
    messages = _parse_inbound(payload)
    statuses = _parse_status(payload)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.from_ == "541130946950"
    assert msg.to == "5491100000000"
    assert msg.message_id == "inbound-msg-002"
    assert msg.text == "Hola live"
    assert statuses == []


def test_parse_inbound_sender_dict_with_phone() -> None:
    """Gupshup v2 Live sends sender as a dict with 'phone' key."""
    payload = {
        "sender": {"phone": "5491122334455"},
        "destination": "5491155667788",
        "type": "text",
        "payload": {"text": "Hello from dict sender"},
    }
    messages = _parse_inbound(payload)
    assert len(messages) == 1
    assert messages[0].from_ == "5491122334455"


# ---------------------------------------------------------------------------
# Status parsing tests (ported from V360)
# ---------------------------------------------------------------------------


def test_parse_status_minimal_payload() -> None:
    payload = {
        "status": {
            "messageId": "msg-999",
            "status": "DELIVERED",
            "timestamp": "1700000001",
        }
    }
    statuses = _parse_status(payload)
    assert len(statuses) == 1
    st = statuses[0]
    assert st["provider"] == "gupshup"
    assert st["service"] == "whatsapp"
    assert st["message_id"] == "msg-999"
    assert st["status"] == "delivered"
    assert st["timestamp"] == "1700000001"


def test_parse_status_message_event_failed_payload() -> None:
    payload = {
        "id": "whatsapp-msg-id-123",
        "gsId": "gs-id-123",
        "type": "failed",
        "destination": "5491130946950",
        "payload": {
            "code": 470,
            "reason": "Message failed because more than 24 hours have passed.",
        },
    }
    statuses = _parse_status(payload)
    inbound = _parse_inbound(payload)
    assert len(statuses) == 1
    st = statuses[0]
    assert st["message_id"] == "gs-id-123"
    assert st["status"] == "failed"
    assert inbound == []


def test_parse_status_message_event_wrapper_delivered() -> None:
    payload = {
        "app": "team360dev",
        "timestamp": 1770565000000,
        "version": 2,
        "type": "message-event",
        "payload": {
            "id": "status-msg-001",
            "gsId": "gs-status-001",
            "type": "delivered",
            "timestamp": "1770565000",
        },
    }
    statuses = _parse_status(payload)
    messages = _parse_inbound(payload)
    assert len(statuses) == 1
    assert statuses[0]["message_id"] == "gs-status-001"
    assert statuses[0]["status"] == "delivered"
    assert messages == []


def test_parse_status_normalized_values() -> None:
    """Status values are normalized to canonical form."""
    for raw, expected in [
        ("ACCEPTED", "queued"),
        ("QUEUED", "queued"),
        ("ENQUEUED", "queued"),
        ("SUBMITTED", "queued"),
        ("SENT", "sent"),
        ("DELIVERED", "delivered"),
        ("READ", "read"),
        ("FAILED", "failed"),
        ("FAIL", "failed"),
        ("ERROR", "failed"),
    ]:
        payload = {"status": {"messageId": "m1", "status": raw, "timestamp": "0"}}
        statuses = _parse_status(payload)
        assert len(statuses) == 1
        assert statuses[0]["status"] == expected, f"Raw={raw}"


# ---------------------------------------------------------------------------
# normalize_inbound tests (Team360 domain contract)
# ---------------------------------------------------------------------------


def test_normalize_inbound_minimal() -> None:
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "hola",
            "timestamp": "1700000000",
            "id": "msg-123",
        }
    }
    message = normalize_inbound(payload)
    assert message.provider == "gupshup"
    assert message.channel == "whatsapp"
    assert message.external_message_id == "msg-123"
    assert message.external_thread_id == "msg-123"
    assert message.sender == "5491122334455"
    assert message.recipients == ("14155551234",)
    assert message.text_body == "hola"
    assert message.subject == ""


def test_normalize_inbound_wrapper() -> None:
    payload = {
        "app": "team360dev",
        "version": 2,
        "type": "message",
        "payload": {
            "id": "inbound-msg-001",
            "source": "541130946950",
            "destination": "5491100000000",
            "type": "text",
            "payload": {"text": "OK DobleVia"},
        },
    }
    message = normalize_inbound(payload)
    assert message.sender == "541130946950"
    assert message.recipients == ("5491100000000",)
    assert message.text_body == "OK DobleVia"
    assert message.external_message_id == "inbound-msg-001"


def test_normalize_inbound_event_wrapper_live() -> None:
    payload = {
        "app": "team360dev",
        "version": 2,
        "type": "message-event",
        "sender": {"phone": "541130946950"},
        "destination": "5491100000000",
        "payload": {
            "id": "inbound-msg-002",
            "type": "text",
            "payload": {"text": "Hola live"},
        },
    }
    message = normalize_inbound(payload)
    assert message.sender == "541130946950"
    assert message.text_body == "Hola live"
    assert message.channel == "whatsapp"


def test_normalize_inbound_preserves_metadata() -> None:
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "test",
            "id": "msg-meta",
        }
    }
    message = normalize_inbound(payload)
    assert "wa_id" in message.metadata
    assert "raw" in message.metadata
    assert message.metadata["wa_id"] == "5491122334455"


def test_normalize_inbound_raises_on_empty() -> None:
    with pytest.raises(ValueError, match="No inbound message"):
        normalize_inbound({"status": {"messageId": "m1", "status": "delivered"}})


def test_normalize_inbound_raises_on_garbage() -> None:
    with pytest.raises(ValueError, match="No inbound message"):
        normalize_inbound({"foo": "bar"})


# ---------------------------------------------------------------------------
# is_status_event / is_inbound_message
# ---------------------------------------------------------------------------


def test_is_status_event_true_for_status() -> None:
    payload = {"status": {"messageId": "m1", "status": "delivered"}}
    assert is_status_event(payload) is True


def test_is_status_event_false_for_message() -> None:
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "hola",
            "id": "msg-1",
        }
    }
    assert is_status_event(payload) is False


def test_is_inbound_message_true_for_message() -> None:
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "hola",
            "id": "msg-1",
        }
    }
    assert is_inbound_message(payload) is True


def test_is_inbound_message_false_for_status() -> None:
    payload = {"status": {"messageId": "m1", "status": "delivered"}}
    assert is_inbound_message(payload) is False
