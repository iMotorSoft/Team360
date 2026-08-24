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
    first_response_sla_seconds: int | None = None


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
    "reparacion_de_alumbrado_publico_poste_de_luz": "alumbrado",
    "alumbrado_publico_reparacion_de_luminaria": "alumbrado",
    "street_lighting": "alumbrado",
    "baches": "baches",
    "bache": "baches",
    "pozo": "baches",
    "pozos": "baches",
    "pavimento_roto": "baches",
    "agujero_en_la_calzada": "baches",
    "residuos": "residuos",
    "residuo": "residuos",
    "basura": "residuos",
    "recoleccion_de_basura": "residuos",
    "residuos_acumulados": "residuos",
    "contenedor_desbordado": "residuos",
}

# Closed vocabulary offered to the intake interpreter. `tentative_category`
# must be one of these canonical values or null; descriptive detail belongs in
# `description` / `context_notes`, never in `tentative_category`.
CANONICAL_CATEGORIES: tuple[str, ...] = ("alumbrado", "baches", "residuos")


def normalize_routing_category(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_text.lower())).strip("_")


def resolve_sector_id(tentative_category: str | None) -> str | None:
    """Map a normalized intake category to a stable sector id.

    Exact normalized matches are resolved first. Compound labels that merely
    LEAD with a known catalog label (e.g. "Alumbrado público - luminaria
    apagada") are resolved to the leading label's sector. Labels whose leading
    token is not part of the catalog (e.g. "robo de luminaria") stay
    unresolved instead of being forced into a sector.
    """
    normalized = normalize_routing_category(tentative_category)
    if not normalized:
        return None
    sector = _CATEGORY_TO_SECTOR.get(normalized)
    if sector is not None:
        return sector
    for label in sorted(_CATEGORY_TO_SECTOR, key=len, reverse=True):
        if normalized.startswith(label + "_"):
            return _CATEGORY_TO_SECTOR[label]
    return None


def routing_rfc_message_id(
    request_id: str, routing_key: str = INITIAL_N1_ROUTING_KEY
) -> str:
    """Stable reconciliation key across DB retries and Gmail timeouts."""
    safe_request_id = re.sub(r"[^a-zA-Z0-9-]", "", request_id)
    if not safe_request_id:
        raise ValueError("Flow request id cannot produce an RFC Message-ID.")
    safe_routing_key = re.sub(r"[^a-zA-Z0-9-]", "-", routing_key).strip("-")
    if not safe_routing_key:
        raise ValueError("Flow routing key cannot produce an RFC Message-ID.")
    return f"<team360-flow-{safe_routing_key}-{safe_request_id}@alquimiablue.com>"
