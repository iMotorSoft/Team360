"""WhatsApp provider contracts for Team360 messaging.

These protocols define the internal boundary between provider-specific WhatsApp
payloads and the canonical Team360 messaging domain. Flow and application code
depend only on these contracts, never on Gupshup, Meta, or any external API.

Inbound:
    Provider payload → WhatsAppInboundNormalizer → InboundMessage

Outbound:
    Application → WhatsAppMessageSenderPort → provider adapter (future)
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .messages import InboundMessage, OutboundMessageReceipt

WHATSAPP_CHANNEL: str = "whatsapp"


@runtime_checkable
class WhatsAppInboundNormalizer(Protocol):
    """Transform a provider-specific WhatsApp payload into canonical InboundMessage.

    The normalizer receives the raw payload dict (as delivered by the provider
    webhook or API) and returns a provider-neutral InboundMessage. Provider-
    specific attributes (wa_id, phone_number_id, media, raw event type) go
    into the metadata mapping, never into the canonical fields.

    Implementations may include GupshupWhatsAppInboundNormalizer,
    MetaWhatsAppInboundNormalizer, or test fakes.
    """

    def normalize(self, payload: Mapping[str, Any]) -> InboundMessage: ...


@runtime_checkable
class WhatsAppMessageSenderPort(Protocol):
    """Send a text message to a WhatsApp destination.

    The sender receives a destination (phone number in E.164 or provider-
    normalized format) and a text body. It returns an OutboundMessageReceipt
    with provider-assigned identifiers.

    Implementations may include GupshupWhatsAppSender, MetaWhatsAppSender,
    or test fakes. No implementation in this gate performs real I/O.
    """

    def send_text(self, *, destination: str, text: str) -> OutboundMessageReceipt: ...


__all__ = [
    "WHATSAPP_CHANNEL",
    "WhatsAppInboundNormalizer",
    "WhatsAppMessageSenderPort",
]
