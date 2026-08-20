"""HTTP client for Gupshup WhatsApp API.

Posts text messages to the Gupshup messaging endpoint.
All secrets come from GupshupConfig, never hardcoded.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from .config import GupshupConfig

MESSAGE_PATH = "/wa/api/v1/msg"
MAX_ERROR_BODY_CHARS = 2000
logger = logging.getLogger(__name__)


class GupshupHTTPError(RuntimeError):
    """Raised when Gupshup returns a non-success HTTP status."""

    def __init__(
        self, *, status_code: int, response_text: str, url: str
    ) -> None:
        super().__init__(f"Gupshup HTTP error ({status_code})")
        self.status_code = status_code
        self.response_text = response_text
        self.url = url


class GupshupWhatsAppClient:
    """Async HTTP client for the Gupshup WhatsApp send API."""

    def __init__(
        self,
        config: GupshupConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or GupshupConfig.from_global()
        self._client = client

    @property
    def config(self) -> GupshupConfig:
        return self._config

    async def send_text(self, to: str, text: str) -> dict[str, Any]:
        """Send a text message via Gupshup.

        Returns the parsed JSON response from Gupshup on success.
        Raises GupshupHTTPError on non-2xx status.
        """
        url = _join_url(self._config.base_url, MESSAGE_PATH)
        headers = {"apikey": self._config.api_key}
        payload = {
            "channel": "whatsapp",
            "source": self._config.source_number,
            "destination": to,
            "message": json.dumps(
                {"type": "text", "text": text},
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            "src.name": self._config.app_name,
        }

        async def _post(http_client: httpx.AsyncClient) -> dict[str, Any]:
            started_at = time.perf_counter()
            response = await http_client.post(
                url,
                data=_encode_payload(payload),
                headers=headers,
                timeout=15.0,
            )
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "GUPSHUP_HTTP_SEND source=%s url=%s status=%s duration_ms=%s",
                self._config.source_number or "-",
                url,
                response.status_code,
                duration_ms,
            )
            if response.status_code >= 400:
                raise GupshupHTTPError(
                    status_code=response.status_code,
                    response_text=_truncate_error_text(response.text),
                    url=str(response.request.url),
                )
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}

        if self._client is None:
            async with httpx.AsyncClient() as http_client:
                return await _post(http_client)
        return await _post(self._client)


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


def _encode_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Encode payload values to strings for form-data submission."""
    encoded: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            encoded[key] = json.dumps(
                value, separators=(",", ":"), ensure_ascii=False
            )
        elif value is None:
            continue
        else:
            encoded[key] = str(value)
    return encoded


def _truncate_error_text(text: str) -> str:
    if len(text) <= MAX_ERROR_BODY_CHARS:
        return text
    return f"{text[:MAX_ERROR_BODY_CHARS]}... [truncated]"
