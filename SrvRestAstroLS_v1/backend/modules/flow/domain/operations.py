"""Operational reply contracts for assigned Flow requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OperationalStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"


class OperationalAction(StrEnum):
    ACK_OR_PROGRESS = "ACK_OR_PROGRESS"
    AMBIGUOUS = "AMBIGUOUS"
    UNRELATED = "UNRELATED"
    UNSUPPORTED_OPERATIONAL_ACTION = "UNSUPPORTED_OPERATIONAL_ACTION"


@dataclass(frozen=True, slots=True)
class OperationalRoutingContext:
    routing_id: str
    request_id: str
    conversation_id: str
    routing_key: str
    level: int
    routing_status: str
    destination: str
    outbound_external_message_id: str
    outbound_rfc_message_id: str | None
    outbound_observed_rfc_message_id: str | None


@dataclass(frozen=True, slots=True)
class CorrelatedOperationalReply:
    context: OperationalRoutingContext
    method: str


@dataclass(frozen=True, slots=True)
class OperationalInterpretation:
    action: OperationalAction
    summary: str
    provider: str
    model: str
    usage: dict
    latency_ms: int | None


@dataclass(frozen=True, slots=True)
class OperationalWorkState:
    request_id: str
    routing_id: str
    status: OperationalStatus
    first_response_at: datetime | None
    first_responder: str | None


_REQUEST_TOKEN = re.compile(
    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\b",
    re.IGNORECASE,
)
_ROUTING_TOKEN = re.compile(r"\[R:([a-z][a-z0-9_]{0,63})\]", re.IGNORECASE)


def request_id_from_subject(subject: str) -> str | None:
    match = _REQUEST_TOKEN.search(subject)
    return match.group(1).lower() if match else None


def routing_key_from_subject(subject: str) -> str | None:
    match = _ROUTING_TOKEN.search(subject)
    return match.group(1).lower() if match else None


def rfc_reference_ids(in_reply_to: str, references: str) -> tuple[str, ...]:
    values = re.findall(r"<[^<>\s]+@[^<>\s]+>", f"{in_reply_to} {references}")
    return tuple(dict.fromkeys(values))
