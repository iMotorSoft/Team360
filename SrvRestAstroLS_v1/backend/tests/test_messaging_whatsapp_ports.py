"""WhatsApp provider port contract tests.

Validates the WhatsAppInboundNormalizer and WhatsAppMessageSenderPort protocols
with fake implementations. No real provider code, no network I/O, no secrets.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from modules.messaging.domain import (
    InboundMessage,
    OutboundMessageReceipt,
    WHATSAPP_CHANNEL,
    WhatsAppInboundNormalizer,
    WhatsAppMessageSenderPort,
)


# ---------------------------------------------------------------------------
# Fake implementations
# ---------------------------------------------------------------------------
class FakeWhatsAppNormalizer:
    """Test double that satisfies WhatsAppInboundNormalizer.

    Expects a payload with:
    - provider: str
    - message_id: str
    - thread_id: str
    - sender: str (phone/wa_id)
    - recipient: str (phone/wa_id)
    - text: str
    - timestamp: str (ISO format)
    - metadata: dict (optional, provider-specific)
    """

    def normalize(self, payload: Mapping[str, Any]) -> InboundMessage:
        return InboundMessage(
            provider=str(payload["provider"]),
            channel=WHATSAPP_CHANNEL,
            external_message_id=str(payload["message_id"]),
            external_thread_id=str(payload["thread_id"]),
            sender=str(payload["sender"]),
            recipients=(str(payload["recipient"]),),
            subject="",
            text_body=str(payload.get("text", "")),
            received_at=datetime.fromisoformat(str(payload["timestamp"])),
            metadata=dict(payload.get("metadata", {})),
        )


class FakeWhatsAppSender:
    """Test double that satisfies WhatsAppMessageSenderPort.

    Captures all send_text invocations for assertion. Returns deterministic
    receipts with fake provider IDs.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self._counter = 0

    def send_text(self, *, destination: str, text: str) -> OutboundMessageReceipt:
        self._counter += 1
        self.sent.append({
            "destination": destination,
            "text": text,
        })
        return OutboundMessageReceipt(
            external_message_id=f"fake-wa-msg-{self._counter}",
            external_thread_id=f"fake-wa-thread-{destination}",
        )


# ---------------------------------------------------------------------------
# Inbound contract tests
# ---------------------------------------------------------------------------
def test_fake_normalizer_satisfies_protocol():
    """FakeWhatsAppNormalizer satisfies WhatsAppInboundNormalizer Protocol."""
    normalizer = FakeWhatsAppNormalizer()
    assert isinstance(normalizer, WhatsAppInboundNormalizer)


def test_normalizer_produces_inbound_message():
    """Normalizer produces canonical InboundMessage from provider payload."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "gupshup",
        "message_id": "msg-123",
        "thread_id": "thread-456",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Hola, necesito ayuda",
        "timestamp": "2026-08-19T10:30:00+00:00",
        "metadata": {"wa_id": "5491122334455"},
    }
    message = normalizer.normalize(payload)
    assert isinstance(message, InboundMessage)


def test_normalizer_sets_channel_to_whatsapp():
    """Normalizer sets channel='whatsapp' regardless of provider."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "meta",
        "message_id": "wamid.123",
        "thread_id": "thread-789",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.channel == WHATSAPP_CHANNEL
    assert message.channel == "whatsapp"


def test_normalizer_preserves_sender():
    """Normalizer preserves sender (phone/wa_id) from payload."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "gupshup",
        "message_id": "msg-1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.sender == "5491122334455"


def test_normalizer_preserves_recipient():
    """Normalizer preserves recipient in recipients tuple."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "meta",
        "message_id": "wamid.1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.recipients == ("5491155667788",)


def test_normalizer_preserves_text():
    """Normalizer preserves text body from payload."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "gupshup",
        "message_id": "msg-1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Hola, necesito ayuda con mi reclamo",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.text_body == "Hola, necesito ayuda con mi reclamo"


def test_normalizer_preserves_provider_message_id():
    """Normalizer preserves provider message ID in external_message_id."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "meta",
        "message_id": "wamid.HBgLMzUxMTEyMjMzNDQ1NRUCABIYFDNFQz...==",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.external_message_id == "wamid.HBgLMzUxMTEyMjMzNDQ1NRUCABIYFDNFQz...=="


def test_normalizer_preserves_thread_identity():
    """Normalizer preserves thread/conversation identity."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "gupshup",
        "message_id": "msg-1",
        "thread_id": "conversation-abc-123",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.external_thread_id == "conversation-abc-123"


def test_normalizer_preserves_metadata():
    """Normalizer preserves provider-specific metadata without contaminating canonical fields."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "meta",
        "message_id": "wamid.1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
        "metadata": {
            "wa_id": "5491122334455",
            "phone_number_id": "1234567890",
            "media_count": 0,
            "raw_event_type": "message",
        },
    }
    message = normalizer.normalize(payload)
    assert message.metadata["wa_id"] == "5491122334455"
    assert message.metadata["phone_number_id"] == "1234567890"
    assert message.metadata["media_count"] == 0
    assert message.metadata["raw_event_type"] == "message"
    assert message.subject == ""
    assert message.channel == "whatsapp"


def test_normalizer_sets_empty_subject():
    """WhatsApp has no subject; normalizer sets subject=''."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "gupshup",
        "message_id": "msg-1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.subject == ""


def test_normalizer_parses_timestamp():
    """Normalizer parses ISO timestamp into datetime."""
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "meta",
        "message_id": "wamid.1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Test",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert isinstance(message.received_at, datetime)
    assert message.received_at.year == 2026
    assert message.received_at.month == 8
    assert message.received_at.day == 19


# ---------------------------------------------------------------------------
# Outbound contract tests
# ---------------------------------------------------------------------------
def test_fake_sender_satisfies_protocol():
    """FakeWhatsAppSender satisfies WhatsAppMessageSenderPort Protocol."""
    sender = FakeWhatsAppSender()
    assert isinstance(sender, WhatsAppMessageSenderPort)


def test_sender_receives_destination_and_text():
    """send_text receives destination and text correctly."""
    sender = FakeWhatsAppSender()
    sender.send_text(destination="5491122334455", text="Hola vecino")
    assert len(sender.sent) == 1
    assert sender.sent[0]["destination"] == "5491122334455"
    assert sender.sent[0]["text"] == "Hola vecino"


def test_sender_returns_outbound_receipt():
    """send_text returns OutboundMessageReceipt."""
    sender = FakeWhatsAppSender()
    receipt = sender.send_text(destination="5491122334455", text="Test")
    assert isinstance(receipt, OutboundMessageReceipt)
    assert receipt.external_message_id.startswith("fake-wa-msg-")
    assert receipt.external_thread_id.startswith("fake-wa-thread-")


def test_sender_captures_invocation():
    """Fake sender captures all invocations for assertion."""
    sender = FakeWhatsAppSender()
    sender.send_text(destination="5491111111111", text="First")
    sender.send_text(destination="5491122222222", text="Second")
    sender.send_text(destination="5491133333333", text="Third")
    assert len(sender.sent) == 3
    assert sender.sent[0]["text"] == "First"
    assert sender.sent[1]["text"] == "Second"
    assert sender.sent[2]["text"] == "Third"


def test_sender_no_network_access():
    """Fake sender performs no I/O; purely in-memory."""
    sender = FakeWhatsAppSender()
    receipt = sender.send_text(destination="5491122334455", text="Test")
    assert receipt.external_message_id
    assert len(sender.sent) == 1


def test_sender_receipt_contains_provider_ids():
    """Receipt contains provider-assigned identifiers."""
    sender = FakeWhatsAppSender()
    receipt = sender.send_text(destination="5491122334455", text="Test")
    assert receipt.external_message_id
    assert receipt.external_thread_id
    assert "5491122334455" in receipt.external_thread_id


# ---------------------------------------------------------------------------
# Provider independence
# ---------------------------------------------------------------------------
def _whatsapp_contract_source() -> str:
    import modules.messaging.domain.whatsapp as wa_module

    return Path(wa_module.__file__).read_text()


def test_contracts_do_not_import_gupshup():
    """WhatsApp contracts do not import Gupshup provider modules."""
    source = _whatsapp_contract_source()
    assert "from modules.messaging.providers.gupshup" not in source
    assert "import gupshup" not in source.lower()


def test_contracts_do_not_import_meta():
    """WhatsApp contracts do not import Meta provider modules."""
    source = _whatsapp_contract_source()
    assert "from modules.messaging.providers.meta" not in source
    assert "import meta" not in source.lower()


def test_contracts_do_not_call_external_apis():
    """WhatsApp contracts do not call external APIs."""
    source = _whatsapp_contract_source()
    assert "api.gupshup.io" not in source
    assert "graph.facebook.com" not in source
    assert "import httpx" not in source
    assert "import requests" not in source
    assert "import aiohttp" not in source


def test_contracts_do_not_require_credentials():
    """WhatsApp contracts do not require credentials or environment access."""
    source = _whatsapp_contract_source()
    assert "GUPSHUP_API_KEY" not in source
    assert "GUPSHUP_APP_NAME" not in source
    assert "META_WABA_TOKEN" not in source
    assert "META_APP_SECRET" not in source
    assert "os.environ" not in source
    assert "getenv" not in source


# ---------------------------------------------------------------------------
# End-to-end flow compatibility
# ---------------------------------------------------------------------------
def test_inbound_message_compatible_with_flow_intake():
    """WhatsApp InboundMessage is compatible with Flow intake service signature.

    Flow intake expects InboundMessage with provider, channel, sender, etc.
    WhatsApp normalizer produces exactly that shape.
    """
    normalizer = FakeWhatsAppNormalizer()
    payload = {
        "provider": "gupshup",
        "message_id": "msg-1",
        "thread_id": "thread-1",
        "sender": "5491122334455",
        "recipient": "5491155667788",
        "text": "Poste apagado en Calle 123",
        "timestamp": "2026-08-19T10:30:00+00:00",
    }
    message = normalizer.normalize(payload)
    assert message.provider == "gupshup"
    assert message.channel == "whatsapp"
    assert message.sender == "5491122334455"
    assert message.text_body == "Poste apagado en Calle 123"
    assert message.external_message_id == "msg-1"
    assert message.external_thread_id == "thread-1"


def test_outbound_receipt_compatible_with_existing_domain():
    """WhatsApp OutboundMessageReceipt is the same type used by Gmail.

    No new receipt type needed; WhatsApp reuses the canonical domain type.
    """
    sender = FakeWhatsAppSender()
    receipt = sender.send_text(destination="5491122334455", text="Test")
    assert isinstance(receipt, OutboundMessageReceipt)
    assert hasattr(receipt, "external_message_id")
    assert hasattr(receipt, "external_thread_id")
