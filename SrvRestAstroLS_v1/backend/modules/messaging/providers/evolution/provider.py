"""Only this adapter knows Evolution URLs, endpoints and wire formats."""
from __future__ import annotations

import re

import httpx

from modules.messaging.domain.delivery import MessagingSendError
from modules.messaging.domain.egress import OutboundIdentity, validate_egress
from modules.messaging.domain.messages import OutboundMessageReceipt
from .config import EvolutionConfig

# Meta rejects a text body longer than this. The outbound guard keeps every
# message inside it; the adapter refuses to send anything longer anyway.
META_TEXT_LIMIT = 4096
_REJECTION_STATUSES = {'error', 'failed', 'rejected', 'failure'}
# Redacted reasons only: no provider payload is ever copied into a message.
_REJECTION_REASONS = (
    (re.compile(r'too long|too large|exceed|character limit', re.IGNORECASE),
     'provider_text_too_long'),
    (re.compile(r'not a valid recipient|recipient.*(invalid|not found)', re.IGNORECASE),
     'provider_recipient_rejected'),
    (re.compile(r'unsupported|invalid parameter|invalid argument', re.IGNORECASE),
     'provider_payload_rejected'),
)


def _rejection_reason(payload) -> str | None:
    """An explicit provider rejection is a confirmed failure, not an unknown one."""
    if not isinstance(payload, dict):
        return None
    status = payload.get('status')
    key = payload.get('key')
    key_status = key.get('status') if isinstance(key, dict) else None
    failed = (isinstance(status, str) and status.strip().lower() in _REJECTION_STATUSES
              or isinstance(key_status, str) and key_status.strip().lower() in _REJECTION_STATUSES)
    errors = payload.get('errors')
    has_errors = (isinstance(errors, list) and bool(errors)) or bool(payload.get('error'))
    if not (failed or has_errors):
        return None
    haystack = []
    for value in (payload.get('message'), payload.get('error'), errors):
        if isinstance(value, str):
            haystack.append(value)
        elif isinstance(value, (dict, list)):
            haystack.append(str(value))
    text = ' '.join(haystack)
    for pattern, code in _REJECTION_REASONS:
        if pattern.search(text):
            return code
    return 'provider_message_rejected'


class EvolutionProvider:
    """Implements the existing synchronous WhatsAppMessageSenderPort."""

    def __init__(self, config: EvolutionConfig, *, transport=None):
        self._config = config
        self._transport = transport

    def send_intent(self, *, destination: str, text: str,
                    identity: OutboundIdentity) -> OutboundMessageReceipt:
        """V1 never falls back to the identity-less legacy request."""
        if identity.provider_instance != self._config.instance:
            raise MessagingSendError('provider_instance_mismatch')
        if not re.fullmatch(r'[1-9][0-9]{6,14}', destination) or not text:
            raise MessagingSendError('invalid_destination_or_text')
        if len(text) > META_TEXT_LIMIT:
            raise MessagingSendError('provider_text_too_long')
        try:
            with httpx.Client(timeout=self._config.timeout, transport=self._transport,
                              trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    f'{self._config.base_url}/message/sendText/{self._config.instance}',
                    headers={'apikey': self._config.api_key},
                    json={'number': destination, 'text': text, 'team360_egress': identity.wire()},
                )
        except httpx.HTTPError:
            # Even a disconnected response must not cause a new attempt.
            raise MessagingSendError('provider_transport_unknown', uncertain=True) from None
        try:
            payload = response.json()
            evidence = validate_egress(payload['egress'], identity)
        except (ValueError, KeyError, TypeError):
            raise MessagingSendError('provider_egress_invalid', uncertain=True) from None
        if evidence['acceptance'] == 'ACCEPTED':
            return OutboundMessageReceipt(evidence['provider_message_id'], destination, evidence)
        raise MessagingSendError(
            'provider_rejected' if evidence['acceptance'] == 'REJECTED' else 'provider_unknown',
            uncertain=evidence['acceptance'] == 'UNKNOWN', egress=evidence)

    def send_text(self, *, destination: str, text: str) -> OutboundMessageReceipt:
        if not re.fullmatch(r"[1-9][0-9]{6,14}", destination) or not text:
            raise MessagingSendError("invalid_destination_or_text")
        if len(text) > META_TEXT_LIMIT:
            # A body the provider will reject is a confirmed failure, not an
            # unknown outcome: it must be visible and must not be retried.
            raise MessagingSendError("provider_text_too_long")
        try:
            with httpx.Client(timeout=self._config.timeout, transport=self._transport,
                              trust_env=False, follow_redirects=False) as client:
                response = client.post(
                    f"{self._config.base_url}/message/sendText/{self._config.instance}",
                    headers={"apikey": self._config.api_key},
                    json={"number": destination, "text": text},
                )
        except httpx.TimeoutException:
            raise MessagingSendError("provider_timeout", uncertain=True) from None
        except httpx.ConnectError:
            raise MessagingSendError("provider_unavailable") from None
        except httpx.HTTPError:
            raise MessagingSendError("provider_transport_error", uncertain=True) from None
        if not 200 <= response.status_code < 300:
            raise MessagingSendError("provider_http_error", uncertain=response.status_code >= 500)
        try:
            payload = response.json()
        except ValueError:
            raise MessagingSendError("provider_invalid_response", uncertain=True) from None
        # A provider may answer 2xx and still report an explicit rejection.
        # That is a confirmed failure: never an uncertain outcome to retry.
        reason = _rejection_reason(payload)
        if reason is not None:
            raise MessagingSendError(reason)
        try:
            key = payload["key"]
            message_id = key["id"]
            if (key.get("fromMe") is not True or not isinstance(message_id, str)
                    or not message_id or key.get("remoteJid") != destination + "@s.whatsapp.net"):
                raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError):
            raise MessagingSendError("provider_invalid_response", uncertain=True) from None
        return OutboundMessageReceipt(message_id, destination)
