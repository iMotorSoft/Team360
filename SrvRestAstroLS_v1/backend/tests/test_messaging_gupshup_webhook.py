"""Gupshup WhatsApp webhook tests.

Tests the POST /webhooks/messaging/gupshup/whatsapp endpoint with
various payload shapes using Litestar TestClient.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# Ensure the app can be imported
from ls_iMotorSoft_Srv01 import create_app  # noqa: E402

from litestar.testing import TestClient  # noqa: E402


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app=app) as c:
        yield c


WEBHOOK_PATH = "/webhooks/messaging/gupshup/whatsapp"


# ---------------------------------------------------------------------------
# Minimal inbound message
# ---------------------------------------------------------------------------


def test_webhook_minimal_inbound(client) -> None:
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "hola",
            "timestamp": "1700000000",
            "id": "msg-123",
        }
    }
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "message"
    assert data["message_id"] == "msg-123"
    assert data["sender"] == "5491122334455"


# ---------------------------------------------------------------------------
# Wrapper message (type=message)
# ---------------------------------------------------------------------------


def test_webhook_wrapper_message(client) -> None:
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
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "message"
    assert data["message_id"] == "inbound-msg-001"
    assert data["sender"] == "541130946950"


# ---------------------------------------------------------------------------
# Event wrapper live (type=message-event with sender dict)
# ---------------------------------------------------------------------------


def test_webhook_event_wrapper_live(client) -> None:
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
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "message"
    assert data["sender"] == "541130946950"


# ---------------------------------------------------------------------------
# Status event
# ---------------------------------------------------------------------------


def test_webhook_status_event(client) -> None:
    payload = {
        "status": {
            "messageId": "msg-999",
            "status": "DELIVERED",
            "timestamp": "1700000001",
        }
    }
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "status"


# ---------------------------------------------------------------------------
# Failed status event
# ---------------------------------------------------------------------------


def test_webhook_failed_status_event(client) -> None:
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
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "status"


# ---------------------------------------------------------------------------
# Unknown / ignored event
# ---------------------------------------------------------------------------


def test_webhook_unknown_event(client) -> None:
    # Payload with type field but no recognized structure is classified as
    # a status event by the Gupshup mapper (expected V360-port behavior).
    payload = {"type": "unknown_event_type", "data": {}}
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "status"


# ---------------------------------------------------------------------------
# Invalid JSON
# ---------------------------------------------------------------------------


def test_webhook_invalid_json(client) -> None:
    response = client.post(
        WEBHOOK_PATH,
        content=b"not json at all",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Empty body
# ---------------------------------------------------------------------------


def test_webhook_empty_body(client) -> None:
    response = client.post(
        WEBHOOK_PATH,
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    # Empty JSON parses as null in some frameworks; expect 200 or 400
    assert response.status_code in (200, 400)


# ---------------------------------------------------------------------------
# Garbage payload (no recognized structure)
# ---------------------------------------------------------------------------


def test_webhook_garbage_payload(client) -> None:
    payload = {"foo": "bar", "baz": 123}
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["event_type"] == "ignored"


# ---------------------------------------------------------------------------
# HTTP method not allowed
# ---------------------------------------------------------------------------


def test_webhook_get_not_allowed(client) -> None:
    response = client.get(WEBHOOK_PATH)
    assert response.status_code in (405, 404)


# ---------------------------------------------------------------------------
# Path is correct
# ---------------------------------------------------------------------------


def test_webhook_path_exists(client) -> None:
    """Verify the webhook path is registered and reachable."""
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "ping",
            "id": "ping-1",
        }
    }
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
