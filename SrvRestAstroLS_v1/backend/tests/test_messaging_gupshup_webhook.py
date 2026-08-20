"""Gupshup WhatsApp webhook tests.

Tests the POST /webhooks/messaging/gupshup/whatsapp endpoint with
various payload shapes using Litestar TestClient.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from ls_iMotorSoft_Srv01 import create_app  # noqa: E402
from litestar.testing import TestClient  # noqa: E402
from modules.messaging.whatsapp_claim import ClaimResult  # noqa: E402


def _mock_claimer(is_new: bool = True) -> MagicMock:
    """Create a mock WhatsAppMessageClaimer."""
    claimer = MagicMock()
    claimer.claim = AsyncMock(
        return_value=ClaimResult(
            is_new=is_new,
            provider_message_id="msg-123",
            sender="5491122334455",
            conversation_id="conv-abc",
            message_id="stored-msg-1",
        )
    )
    return claimer


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app=app) as c:
        yield c


WEBHOOK_PATH = "/webhooks/messaging/gupshup/whatsapp"


# ---------------------------------------------------------------------------
# Minimal inbound message — new
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_minimal_inbound_new(mock_get_claimer, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=True)
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
    assert data["is_new"] is True
    assert data["provider_message_id"] == "msg-123"
    assert data["sender"] == "5491122334455"


# ---------------------------------------------------------------------------
# Duplicate inbound message
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_duplicate_inbound(mock_get_claimer, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=False)
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
    assert data["is_new"] is False
    assert data["provider_message_id"] == "msg-123"


# ---------------------------------------------------------------------------
# Wrapper message (type=message)
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_wrapper_message(mock_get_claimer, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=True)
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
    assert data["is_new"] is True


# ---------------------------------------------------------------------------
# Event wrapper live (type=message-event with sender dict)
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_event_wrapper_live(mock_get_claimer, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=True)
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
    assert data["is_new"] is True


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
# DB error handling
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_db_error_returns_200(mock_get_claimer, client) -> None:
    claimer = MagicMock()
    claimer.claim = AsyncMock(side_effect=RuntimeError("DB connection lost"))
    mock_get_claimer.return_value = claimer
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "test",
            "id": "msg-dberr",
        }
    }
    response = client.post(WEBHOOK_PATH, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "error" in data
