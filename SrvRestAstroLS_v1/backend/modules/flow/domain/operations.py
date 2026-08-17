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
    RESOLUTION_PROPOSED = "RESOLUTION_PROPOSED"
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
    request_status: str = "CONFIRMED"


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
_APPROVAL_TOKEN = re.compile(r"\[R:([0-9a-f]{8,64})\]", re.IGNORECASE)


def request_id_from_subject(subject: str) -> str | None:
    match = _REQUEST_TOKEN.search(subject)
    return match.group(1).lower() if match else None


def routing_key_from_subject(subject: str) -> str | None:
    match = _ROUTING_TOKEN.search(subject)
    return match.group(1).lower() if match else None


def approval_token_from_subject(subject: str) -> str | None:
    match = _APPROVAL_TOKEN.search(subject)
    return match.group(1).lower() if match else None


def rfc_reference_ids(in_reply_to: str, references: str) -> tuple[str, ...]:
    values = re.findall(r"<[^<>\s]+@[^<>\s]+>", f"{in_reply_to} {references}")
    return tuple(dict.fromkeys(values))


def operational_sender_authorized(sender: str, destination: str) -> bool:
    """Return True only when the reply sender belongs to the routing domain.

    Gmail group/forwarding resolution rewrites the ``From`` to a member's
    individual address (proven by the supervisor gate: reply from
    ``mario.rojas@`` for destination ``alumbrado.n1@``), so an exact
    ``sender == destination`` match is too strict. The V1 boundary mirrors
    ``approval_sender_authorized``: the sender must share the destination's
    domain. Citizens and third parties (external domains) are excluded by the
    domain boundary without an extra lookup.
    """
    sender_norm = (sender or "").strip().casefold()
    destination_norm = (destination or "").strip().casefold()
    if "@" not in sender_norm or "@" not in destination_norm:
        return False
    return (
        sender_norm.rsplit("@", 1)[1]
        == destination_norm.rsplit("@", 1)[1]
    )


_AUTOMATED_PRECEDENCE = {"auto_reply"}
_AUTOMATED_BOOLEAN_YES = {"yes", "true"}


def is_automated_message(message) -> bool:
    """Deterministic auto-reply / bounce detection; never an LLM decision.

    RFC 3834 auto-replies advertise ``Auto-Submitted: auto-replied`` or
    ``Precedence: auto_reply``; bounces arrive as ``multipart/report`` with
    ``Delivery Status Notification`` / ``X-Failed-Recipients`` or from
    ``mailer-daemon`` / ``postmaster``. Any of these markers rejects a message
    as a human operational reply (no first response, no SLA MET, no work
    transition).
    """
    metadata = message.metadata or {}
    auto_submitted = str(metadata.get("auto_submitted") or "").strip().lower()
    if auto_submitted and auto_submitted != "no":
        return True
    precedence = str(metadata.get("precedence") or "").strip().lower()
    if precedence in _AUTOMATED_PRECEDENCE:
        return True
    x_autoreply = str(metadata.get("x_autoreply") or "").strip().lower()
    if x_autoreply in _AUTOMATED_BOOLEAN_YES:
        return True
    x_autorespond = str(metadata.get("x_autorespond") or "").strip().lower()
    if x_autorespond and x_autorespond != "no":
        return True
    content_type = str(metadata.get("content_type") or "").lower()
    if content_type.startswith("multipart/report") or "delivery-status" in content_type:
        return True
    if str(metadata.get("x_failed_recipients") or "").strip():
        return True
    sender_domain = (message.sender or "").strip().casefold()
    if sender_domain.startswith("mailer-daemon@") or sender_domain.startswith(
        "postmaster@"
    ):
        return True
    return False
