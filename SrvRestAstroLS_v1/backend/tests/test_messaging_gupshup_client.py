"""Gupshup WhatsApp client tests.

Mock HTTP to validate method, URL, headers, form fields, and error handling
without network access.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from modules.messaging.providers.gupshup.whatsapp.client import (  # noqa: E402
    GupshupHTTPError,
    GupshupWhatsAppClient,
    MESSAGE_PATH,
)
from modules.messaging.providers.gupshup.whatsapp.config import (  # noqa: E402
    GupshupConfig,
)


def _test_config() -> GupshupConfig:
    return GupshupConfig(
        base_url="https://api.gupshup.io",
        api_key="test-api-key-123",
        app_name="team360dev",
        sender_e164="+5491130946950",
        source_number="5491130946950",
    )


def _make_mock_response(status_code: int = 202, json_data: dict | None = None, text: str = "") -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data or {"status": "submitted", "messageId": "m1"}
    mock_response.text = text or str(json_data)
    mock_response.request = MagicMock()
    mock_response.request.url = "https://api.gupshup.io/wa/api/v1/msg"
    return mock_response


def _make_mock_client(response: MagicMock | None = None) -> AsyncMock:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=response or _make_mock_response())
    return mock_client


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def test_client_accepts_config() -> None:
    cfg = _test_config()
    client = GupshupWhatsAppClient(config=cfg)
    assert client.config == cfg


def test_client_exposes_config() -> None:
    cfg = _test_config()
    client = GupshupWhatsAppClient(config=cfg)
    assert client.config.api_key == "test-api-key-123"
    assert client.config.app_name == "team360dev"


# ---------------------------------------------------------------------------
# send_text — success
# ---------------------------------------------------------------------------


def test_send_text_posts_to_correct_url() -> None:
    cfg = _test_config()
    expected_url = f"{cfg.base_url}{MESSAGE_PATH}"

    mock_client = _make_mock_client()
    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    asyncio.run(client.send_text("+5491122334455", "Hola"))

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == expected_url


def test_send_text_sets_apikey_header() -> None:
    cfg = _test_config()
    mock_client = _make_mock_client()

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    asyncio.run(client.send_text("+5491122334455", "Test"))

    call_kwargs = mock_client.post.call_args
    headers = call_kwargs[1].get("headers") or call_kwargs.kwargs.get("headers", {})
    assert headers.get("apikey") == "test-api-key-123"


def test_send_text_includes_channel_whatsapp() -> None:
    cfg = _test_config()
    mock_client = _make_mock_client()

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    asyncio.run(client.send_text("+5491122334455", "Test"))

    call_kwargs = mock_client.post.call_args
    data = call_kwargs[1].get("data") or call_kwargs.kwargs.get("data", {})
    assert data.get("channel") == "whatsapp"


def test_send_text_includes_source_and_destination() -> None:
    cfg = _test_config()
    mock_client = _make_mock_client()

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    asyncio.run(client.send_text("+5491122334455", "Test"))

    call_kwargs = mock_client.post.call_args
    data = call_kwargs[1].get("data") or call_kwargs.kwargs.get("data", {})
    assert data.get("source") == "5491130946950"
    assert data.get("destination") == "+5491122334455"


def test_send_text_includes_src_name() -> None:
    cfg = _test_config()
    mock_client = _make_mock_client()

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    asyncio.run(client.send_text("+5491122334455", "Test"))

    call_kwargs = mock_client.post.call_args
    data = call_kwargs[1].get("data") or call_kwargs.kwargs.get("data", {})
    assert data.get("src.name") == "team360dev"


def test_send_text_returns_json_response() -> None:
    cfg = _test_config()
    mock_response = _make_mock_response(
        json_data={"status": "submitted", "messageId": "gs-msg-789"}
    )
    mock_client = _make_mock_client(mock_response)

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    result = asyncio.run(client.send_text("+5491122334455", "Test"))

    assert result["status"] == "submitted"
    assert result["messageId"] == "gs-msg-789"


# ---------------------------------------------------------------------------
# send_text — error handling
# ---------------------------------------------------------------------------


def test_send_text_raises_on_4xx() -> None:
    cfg = _test_config()
    mock_response = _make_mock_response(status_code=400, text="Bad Request: invalid phone")
    mock_client = _make_mock_client(mock_response)

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    with pytest.raises(GupshupHTTPError) as exc_info:
        asyncio.run(client.send_text("+5491122334455", "Test"))

    assert exc_info.value.status_code == 400
    assert "Bad Request" in exc_info.value.response_text


def test_send_text_raises_on_5xx() -> None:
    cfg = _test_config()
    mock_response = _make_mock_response(status_code=503, text="Service Unavailable")
    mock_client = _make_mock_client(mock_response)

    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    with pytest.raises(GupshupHTTPError) as exc_info:
        asyncio.run(client.send_text("+5491122334455", "Test"))

    assert exc_info.value.status_code == 503


def test_send_text_returns_raw_on_non_json_response() -> None:
    cfg = _test_config()
    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.text = "Accepted"
    mock_response.json.side_effect = ValueError("No JSON")

    mock_client = _make_mock_client(mock_response)
    client = GupshupWhatsAppClient(config=cfg, client=mock_client)
    result = asyncio.run(client.send_text("+5491122334455", "Test"))

    assert result == {"raw": "Accepted"}
