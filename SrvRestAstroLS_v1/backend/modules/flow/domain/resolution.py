"""Supervisor closure, approval and audit domain contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RequestLifecycleStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    RESOLUTION_PENDING_APPROVAL = "RESOLUTION_PENDING_APPROVAL"
    RESOLVED = "RESOLVED"


class ResolutionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ClosureApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DELIVERY_UNCERTAIN = "DELIVERY_UNCERTAIN"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    AMBIGUOUS = "AMBIGUOUS"


AUDIT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ResolutionProposal:
    id: str
    request_id: str
    routing_id: str
    status: ResolutionStatus
    proposed_by: str
    proposed_at: datetime
    source_provider: str
    source_external_message_id: str
    resolution_text: str


@dataclass(frozen=True, slots=True)
class ClosureApproval:
    id: str
    request_id: str
    resolution_id: str
    approver_level: int
    approver_destination: str
    approval_token: str
    status: ClosureApprovalStatus
    outbound_rfc_message_id: str | None
    outbound_external_message_id: str | None
    outbound_observed_rfc_message_id: str | None
    decision_source_external_message_id: str | None
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovalDecisionResult:
    decision: ApprovalDecision
    reason: str


def approval_token_for(provider: str, external_message_id: str) -> str:
    """Deterministic 16-hex approval token from the source message identity.

    A token derived from the correlated inbound message makes the approval
    request practical-exactly-once: if Gmail accepts the send but the DB
    transaction rolls back, a replay regenerates the same token and RFC and
    reconciles the same Sent message instead of re-sending.

    The leading ``a`` keeps the token routing-key-shaped so the operational
    reply correlator never misclassifies a supervisor decision as an
    operational reply via the single-routing subject fallback.
    """
    digest = hashlib.sha256(
        f"flow-closure:{provider}:{external_message_id}".encode("utf-8")
    ).hexdigest()
    return "a" + digest[:15]


def approval_rfc_message_id(approval_token: str) -> str:
    return f"<team360-flow-closure-{approval_token}@alquimiablue.com>"


def approval_sender_authorized(
    sender: str, approver_destination: str, citizen_address: str | None = None
) -> bool:
    """Return True only when ``sender`` is an internal approver, not the citizen.

    A group mailbox (e.g. ``alumbrado.n2@``) resolves replies to a member's
    individual address, so an exact ``sender == approver_destination`` match is
    too strict. The V1 boundary is: same domain as the approver destination AND
    explicitly not the citizen who opened the case.
    """
    sender_norm = (sender or "").strip().casefold()
    approver_norm = (approver_destination or "").strip().casefold()
    if not sender_norm or not approver_norm or "@" not in sender_norm:
        return False
    if sender_norm.rsplit("@", 1)[-1] != approver_norm.rsplit("@", 1)[-1]:
        return False
    citizen_norm = (citizen_address or "").strip().casefold()
    if citizen_norm and sender_norm == citizen_norm:
        return False
    return True


_APPROVE_PATTERN = re.compile(
    r"^\s*(aprobar|aprobado|autorizo\s+cierre|autorizar)\b", re.IGNORECASE
)
_REJECT_PATTERN = re.compile(
    r"^\s*(rechazar|rechazado|rechazo|no\s+aprobar)\b", re.IGNORECASE
)


def deterministic_approval_decision(text: str) -> ApprovalDecision | None:
    """Classify an unambiguous supervisor command without calling the model.

    Only prefix commands are treated as deterministic; anything else returns
    ``None`` so the conservative AI interpreter can decide APPROVE/REJECT/
    AMBIGUOUS without ever closing a case on its own.
    """
    normalized = (text or "").strip()
    if _APPROVE_PATTERN.match(normalized):
        return ApprovalDecision.APPROVE
    if _REJECT_PATTERN.match(normalized):
        return ApprovalDecision.REJECT
    return None


def approval_reason_after_command(text: str) -> str:
    """Return the free-text motive after an explicit command, if any."""
    stripped = (text or "").strip()
    index = stripped.find(":")
    if index < 0:
        return ""
    return stripped[index + 1 :].strip()
