"""Deterministic next-level escalation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


FIRST_RESPONSE_SLA_BREACHED = "FIRST_RESPONSE_SLA_BREACHED"


class EscalationStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class EscalationCandidate:
    request_id: str
    description: str
    location_text: str | None
    origin_channel: str
    sector_id: str
    sector_display_name: str
    from_routing_id: str
    from_level: int
    from_destination: str
    from_assigned_at: datetime
    trigger_sla_id: str
    sla_due_at: datetime
    sla_status: str
    first_response_at: datetime | None


@dataclass(frozen=True, slots=True)
class FlowEscalation:
    id: str
    request_id: str
    sector_id: str
    from_routing_id: str
    from_level: int
    trigger_sla_id: str
    to_level: int
    to_routing_id: str | None
    status: EscalationStatus
    created_at: datetime
    completed_at: datetime | None = None
    last_error_code: str | None = None
