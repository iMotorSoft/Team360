"""Gupshup WhatsApp sender tests.

Validates the WhatsAppMessageSenderPort implementation with mocked HTTP.
Covers success, errors, timeout, non-2xx, malformed response, and receipt shape.
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

from modules.messaging.domain.messages import OutboundMessageReceipt  # noqa: E402
from modules.messaging.domain.whatsapp import WhatsAppMessageSenderPort  # noqa: E402
from modules.messaging.providers.gupshup.whatsapp.client import (  # noqa: E402
    GupshupHTTPError,
    GupshupWhatsAppClient,
)
from modules.messaging.providers.gupshup.whatsapp.config import (  # noqa: E402
    GupshupConfig,
)
from modules.messaging.providers.gupshup.whatsapp.service import (  # noqa: E402
    GupshupWhatsAppSendError,
    GupshupWhatsAppSender,
)


def _test_config() -> GupshupConfig:
    return GupshupConfig(
        base_url="https://api.gupshup.io",
        api_key="test-key",
        app_name="team360dev",
        sender_e164="+5491130946950",
        source_number="5491130946950",
    )


def _make_mock_response(
    status_code: int = 202,
    json_data: dict | None = None,
    text: str = "",
) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data or {
        "status": "submitted",
        "messageId": "gs-msg-default",
    }
    mock_response.text = text or str(json_data)
    mock_response.request = MagicMock()
    mock_response.request.url = "https://api.gupshup.io/wa/api/v1/msg"
    return mock_response


def _make_mock_client(
    response: MagicMock | None = None,
    side_effect: Exception | None = None,
) -> AsyncMock:
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    if side_effect:
        mock_client.post = AsyncMock(side_effect=side_effect)
    else:
        mock_client.post = AsyncMock(return_value=response or _make_mock_response())
    return mock_client


def _make_sender(
    response: MagicMock | None = None,
    side_effect: Exception | None = None,
) -> GupshupWhatsAppSender:
    mock_client = _make_mock_client(response=response, side_effect=side_effect)
    client = GupshupWhatsAppClient(config=_test_config(), client=mock_client)
    return GupshupWhatsAppSender(client=client)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_sender_satisfies_protocol() -> None:
    sender = GupshupWhatsAppSender(config=_test_config())
    assert isinstance(sender, WhatsAppMessageSenderPort)


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


def test_send_text_returns_receipt_on_202_submitted() -> None:
    mock_response = _make_mock_response(
        json_data={"status": "submitted", "messageId": "gs-msg-abc-123"}
    )
    sender = _make_sender(response=mock_response)

    receipt = asyncio.run(
        sender.send_text(destination="+5491122334455", text="Hola vecino")
    )

    assert isinstance(receipt, OutboundMessageReceipt)
    assert receipt.external_message_id == "gs-msg-abc-123"
    assert receipt.external_thread_id == "gs-msg-abc-123"


def test_send_text_uses_message_id_from_response() -> None:
    mock_response = _make_mock_response(
        status_code=200,
        json_data={"messageId": "gs-msg-789"},
    )
    sender = _make_sender(response=mock_response)

    receipt = asyncio.run(
        sender.send_text(destination="+5491122334455", text="Test")
    )

    assert receipt.external_message_id == "gs-msg-789"


def test_send_text_uses_id_fallback_when_no_message_id() -> None:
    mock_response = _make_mock_response(
        status_code=200,
        json_data={"id": "fallback-id-001"},
    )
    sender = _make_sender(response=mock_response)

    receipt = asyncio.run(
        sender.send_text(destination="+5491122334455", text="Test")
    )

    assert receipt.external_message_id == "fallback-id-001"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_send_text_raises_on_http_400() -> None:
    mock_response = _make_mock_response(status_code=400, text="Bad Request: invalid phone")
    sender = _make_sender(response=mock_response)

    with pytest.raises(GupshupWhatsAppSendError) as exc_info:
        asyncio.run(
            sender.send_text(destination="+5491122334455", text="Test")
        )

    assert exc_info.value.upstream_status == 400
    assert "Bad Request" in exc_info.value.upstream_body


def test_send_text_raises_on_http_500() -> None:
    mock_response = _make_mock_response(status_code=500, text="Internal Server Error")
    sender = _make_sender(response=mock_response)

    with pytest.raises(GupshupWhatsAppSendError) as exc_info:
        asyncio.run(
            sender.send_text(destination="+5491122334455", text="Test")
        )

    assert exc_info.value.upstream_status == 500


def test_send_text_raises_on_network_error() -> None:
    sender = _make_sender(side_effect=httpx.ConnectError("Connection refused"))

    with pytest.raises(GupshupWhatsAppSendError) as exc_info:
        asyncio.run(
            sender.send_text(destination="+5491122334455", text="Test")
        )

    assert "Connection refused" in (exc_info.value.upstream_body or "")


def test_send_text_raises_on_timeout() -> None:
    sender = _make_sender(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(GupshupWhatsAppSendError) as exc_info:
        asyncio.run(
            sender.send_text(destination="+5491122334455", text="Test")
        )

    assert "timed out" in (exc_info.value.upstream_body or "")


def test_send_text_raises_on_unexpected_exception() -> None:
    sender = _make_sender(side_effect=RuntimeError("boom"))

    with pytest.raises(GupshupWhatsAppSendError) as exc_info:
        asyncio.run(
            sender.send_text(destination="+5491122334455", text="Test")
        )

    assert "boom" in (exc_info.value.upstream_body or "")


# ---------------------------------------------------------------------------
# Receipt shape
# ---------------------------------------------------------------------------


def test_receipt_has_external_message_id() -> None:
    mock_response = _make_mock_response(
        json_data={"messageId": "gs-msg-shape"}
    )
    sender = _make_sender(response=mock_response)

    receipt = asyncio.run(
        sender.send_text(destination="+5491122334455", text="Test")
    )

    assert hasattr(receipt, "external_message_id")
    assert receipt.external_message_id == "gs-msg-shape"
    assert receipt.external_thread_id == "gs-msg-shape"


def test_receipt_empty_when_no_id_in_response() -> None:
    mock_response = _make_mock_response(
        json_data={"status": "submitted"}
    )
    sender = _make_sender(response=mock_response)

    receipt = asyncio.run(
        sender.send_text(destination="+5491122334455", text="Test")
    )

    assert receipt.external_message_id == ""
    assert receipt.external_thread_id == ""
