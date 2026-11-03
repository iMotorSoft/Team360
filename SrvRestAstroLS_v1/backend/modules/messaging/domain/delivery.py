"""Provider-neutral transport outcomes and delivery events."""
from dataclasses import dataclass
from datetime import datetime


class MessagingSendError(RuntimeError):
    """Sanitized failure: uncertain outcomes must never be automatically retried."""

    def __init__(self, code: str, *, uncertain: bool = False, egress=None):
        super().__init__(code)
        self.code = code
        self.uncertain = uncertain
        self.egress = egress


@dataclass(frozen=True, slots=True)
class DeliveryEvent:
    provider: str
    provider_instance: str
    external_message_id: str
    status: str
    received_at: datetime
