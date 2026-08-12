"""Deterministic Level 1 routing contracts for confirmed Flow requests."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


INITIAL_N1_ROUTING_KEY = "initial_n1"
INITIAL_ROUTING_LEVEL = 1


class RoutingStatus(StrEnum):
    ROUTING_PENDING = "ROUTING_PENDING"
    ASSIGNED = "ASSIGNED"
    ROUTING_UNRESOLVED = "ROUTING_UNRESOLVED"
    ROUTING_FAILED = "ROUTING_FAILED"


class FlowRoutingError(RuntimeError):
    """Base error for typed routing failures."""


class FlowRequestNotFoundError(FlowRoutingError):
    pass


class FlowRequestNotConfirmedError(FlowRoutingError):
    pass


@dataclass(frozen=True, slots=True)
class ConfirmedFlowRequest:
    id: str
    conversation_id: str
    status: str
    description: str
    tentative_category: str | None
    location_text: str | None
    origin_channel: str
    citizen_address: str
    external_thread_id: str


@dataclass(frozen=True, slots=True)
class FlowSector:
    sector_id: str
    display_name: str
    active: bool


@dataclass(frozen=True, slots=True)
class FlowSectorLevel:
    id: str
    sector_id: str
    level: int
    channel: str
    destination: str
    active: bool


@dataclass(frozen=True, slots=True)
class RoutingAssignment:
    id: str
    request_id: str
    routing_key: str
    sector_id: str | None
    level: int
    channel: str | None
    destination: str | None
    status: RoutingStatus
    outbound_rfc_message_id: str | None
    outbound_external_message_id: str | None
    outbound_observed_rfc_message_id: str | None = None
    attempt_count: int = 0
    delivery_uncertain: bool = False
    last_error_code: str | None = None


_CATEGORY_TO_SECTOR = {
    "alumbrado": "alumbrado",
    "alumbrado_publico": "alumbrado",
    "luminaria": "alumbrado",
    "luminarias": "alumbrado",
    "poste_luz": "alumbrado",
    "poste_de_luz": "alumbrado",
    "reparacion_de_alumbrado_publico": "alumbrado",
    "street_lighting": "alumbrado",
}


def normalize_routing_category(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_text.lower())).strip("_")


def resolve_sector_id(tentative_category: str | None) -> str | None:
    """Map an exact normalized intake category to a stable sector id."""
    return _CATEGORY_TO_SECTOR.get(normalize_routing_category(tentative_category))


def routing_rfc_message_id(request_id: str) -> str:
    """Stable reconciliation key across DB retries and Gmail timeouts."""
    safe_request_id = re.sub(r"[^a-zA-Z0-9-]", "", request_id)
    if not safe_request_id:
        raise ValueError("Flow request id cannot produce an RFC Message-ID.")
    return f"<team360-flow-{INITIAL_N1_ROUTING_KEY}-{safe_request_id}@alquimiablue.com>"
