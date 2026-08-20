"""Gupshup WhatsApp service — implements WhatsAppMessageSenderPort.

Wraps the HTTP client to produce canonical OutboundMessageReceipt.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from modules.messaging.domain.messages import OutboundMessageReceipt
from modules.messaging.domain.whatsapp import WhatsAppMessageSenderPort

from .client import GupshupHTTPError, GupshupWhatsAppClient
from .config import GupshupConfig

logger = logging.getLogger(__name__)


class GupshupWhatsAppSendError(Exception):
    """Raised when sending via Gupshup fails."""

    def __init__(
        self,
        message: str,
        *,
        upstream_status: int | None = None,
        upstream_body: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status
        self.upstream_body = upstream_body
        self.url = url


class GupshupWhatsAppSender:
    """Implements WhatsAppMessageSenderPort for Gupshup.

    Usage:
        sender = GupshupWhatsAppSender()
        receipt = await sender.send_text(destination="+5491122334455", text="Hola")
    """

    def __init__(
        self,
        config: GupshupConfig | None = None,
        *,
        client: GupshupWhatsAppClient | None = None,
    ) -> None:
        self._client = client or GupshupWhatsAppClient(config=config)

    async def send_text(
        self, *, destination: str, text: str
    ) -> OutboundMessageReceipt:
        """Send a text message and return a receipt with provider identifiers."""
        try:
            raw = await self._client.send_text(destination, text)
        except GupshupHTTPError as exc:
            raise GupshupWhatsAppSendError(
                "Gupshup send failed",
                upstream_status=exc.status_code,
                upstream_body=exc.response_text,
                url=exc.url,
            ) from exc
        except httpx.HTTPError as exc:
            raise GupshupWhatsAppSendError(
                "Gupshup send failed",
                upstream_body=str(exc),
            ) from exc
        except Exception as exc:
            raise GupshupWhatsAppSendError(
                "Gupshup send failed",
                upstream_body=str(exc),
            ) from exc

        provider_message_id = _extract_message_id(raw)
        return OutboundMessageReceipt(
            external_message_id=provider_message_id,
            external_thread_id=provider_message_id,
        )


def _extract_message_id(raw: dict[str, Any]) -> str:
    """Extract the provider message ID from the Gupshup response.

    Gupshup returns {"status": "submitted", "messageId": "..."} on success.
    """
    message_id = raw.get("messageId") or raw.get("id") or ""
    return str(message_id) if message_id else ""
