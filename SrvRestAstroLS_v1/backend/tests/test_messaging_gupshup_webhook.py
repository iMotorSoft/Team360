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


_WEBHOOK_TOKEN = "gupshup-test-token-at-least-32-characters"
_WEBHOOK_HEADERS = {"x-team360-webhook-token": _WEBHOOK_TOKEN}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("TEAM360_MESSAGING_WEBHOOK_TOKEN", _WEBHOOK_TOKEN)
    app = create_app()
    with TestClient(app=app) as c:
        c.headers.update(_WEBHOOK_HEADERS)
        yield c


WEBHOOK_PATH = "/webhooks/messaging/gupshup/whatsapp"


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_bridge")
@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_missing_auth_configuration_fails_closed_without_side_effects(
    mock_get_claimer, mock_get_bridge, monkeypatch
) -> None:
    monkeypatch.delenv("TEAM360_MESSAGING_WEBHOOK_TOKEN", raising=False)
    with TestClient(app=create_app()) as unauthenticated:
        response = unauthenticated.post(WEBHOOK_PATH, json={"type": "message"})
    assert response.status_code == 503
    mock_get_claimer.assert_not_called()
    mock_get_bridge.assert_not_called()


@pytest.mark.parametrize("headers", [{}, {"x-team360-webhook-token": "wrong"}])
@patch("modules.messaging.webhooks.gupshup_whatsapp._get_bridge")
@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_invalid_credentials_fail_before_side_effects(
    mock_get_claimer, mock_get_bridge, monkeypatch, headers
) -> None:
    monkeypatch.setenv("TEAM360_MESSAGING_WEBHOOK_TOKEN", _WEBHOOK_TOKEN)
    with TestClient(app=create_app()) as unauthenticated:
        response = unauthenticated.post(WEBHOOK_PATH, json={"type": "message"}, headers=headers)
    assert response.status_code == 401
    mock_get_claimer.assert_not_called()
    mock_get_bridge.assert_not_called()


# ---------------------------------------------------------------------------
# Minimal inbound message — new
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_bridge")
@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_minimal_inbound_new(mock_get_claimer, mock_get_bridge, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=True)
    mock_bridge = MagicMock()
    mock_bridge.process = AsyncMock(return_value=MagicMock(
        processed=True, candidate_count=1, confirmed_count=0
    ))
    mock_get_bridge.return_value = mock_bridge
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
    assert data["flow_processed"] is True
    assert data["flow_candidates"] == 1
    # Bridge should be called with conversation_id and state
    mock_bridge.process.assert_called_once()


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
    # Duplicate should NOT trigger flow processing
    assert data.get("flow_processed") is None or data.get("flow_processed") is False


# ---------------------------------------------------------------------------
# Wrapper message (type=message)
# ---------------------------------------------------------------------------


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_bridge")
@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_wrapper_message(mock_get_claimer, mock_get_bridge, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=True)
    mock_bridge = MagicMock()
    mock_bridge.process = AsyncMock(return_value=MagicMock(
        processed=True, candidate_count=1, confirmed_count=0
    ))
    mock_get_bridge.return_value = mock_bridge
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


@patch("modules.messaging.webhooks.gupshup_whatsapp._get_bridge")
@patch("modules.messaging.webhooks.gupshup_whatsapp._get_claimer")
def test_webhook_event_wrapper_live(mock_get_claimer, mock_get_bridge, client) -> None:
    mock_get_claimer.return_value = _mock_claimer(is_new=True)
    mock_bridge = MagicMock()
    mock_bridge.process = AsyncMock(return_value=MagicMock(
        processed=True, candidate_count=1, confirmed_count=0
    ))
    mock_get_bridge.return_value = mock_bridge
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
