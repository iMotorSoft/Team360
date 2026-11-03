"""Provider-neutral message contracts proven by the email intake slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """Normalized inbound message; provider payloads never cross this boundary."""

    provider: str
    channel: str
    external_message_id: str
    external_thread_id: str
    sender: str
    recipients: tuple[str, ...]
    subject: str
    text_body: str
    received_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipients", tuple(self.recipients))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class OutboundMessageReceipt:
    """Provider-neutral external identifiers for a sent message."""

    external_message_id: str
    external_thread_id: str
    egress: Mapping[str, Any] | None = None
