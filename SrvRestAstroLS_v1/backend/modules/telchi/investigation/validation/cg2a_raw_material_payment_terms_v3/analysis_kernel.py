"""Deterministic Telchi CONTADO V1 business-rule kernel.

Commercial classification, settlement behaviour, and collection method are
independent dimensions. This module performs no I/O and never accesses SAP.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

CONTADO_CONFIRMED = "CONTADO_CONFIRMED"
CREDIT_CONFIRMED = "CREDIT_CONFIRMED"
OTHER = "OTHER"
UNRESOLVED = "UNRESOLVED"
IMMEDIATE_SETTLEMENT = "IMMEDIATE_SETTLEMENT"
DELAYED_SETTLEMENT = "DELAYED_SETTLEMENT"


def commercial_classification(commercial_term: str | None, document_date: Any, due_date: Any) -> str:
    """Apply TELCHI_CONTADO_RULE_V1 without consulting payment or settlement facts."""
    if not commercial_term or document_date is None or due_date is None:
        return UNRESOLVED
    if commercial_term == "COMMERCIAL_CASH_TERM" and due_date == document_date:
        return CONTADO_CONFIRMED
    if commercial_term == "COMMERCIAL_CREDIT_TERM":
        return CREDIT_CONFIRMED
    return OTHER


def settlement_behavior(document_date: Any, fully_settled_date: Any, state: str) -> str:
    """Classify economic timing separately from the commercial condition."""
    if state == "PARTIALLY_SETTLED":
        return "PARTIAL"
    if state == "OPEN":
        return "OPEN"
    if state != "FULLY_SETTLED" or document_date is None or fully_settled_date is None:
        return UNRESOLVED
    return IMMEDIATE_SETTLEMENT if fully_settled_date == document_date else DELAYED_SETTLEMENT


def cash_method_is_contado() -> bool:
    return False


def transfer_method_can_be_contado() -> bool:
    return True


def same_day_settlement_is_contado_rule() -> bool:
    return False


def qr_from_method(method: str | None) -> str:
    """QR cannot be inferred from transfer, text, bank, or another method label."""
    return "UNRESOLVED_SOURCE_EVIDENCE"


def payment_method_grain_caveat() -> str:
    return "YES"


def partition_is_exact(parts: Mapping[str, int], expected: int) -> bool:
    return all(value >= 0 for value in parts.values()) and sum(parts.values()) == expected


def pct(numerator: Any, denominator: Any) -> Decimal:
    den = Decimal(str(denominator))
    if den == 0:
        return Decimal("0.0000")
    return (Decimal(str(numerator)) * Decimal(100) / den).quantize(Decimal("0.0001"))


def v1_v2_history_preserved(v1: str, v2: str) -> bool:
    return (
        v1 == "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V1_DEGRADED"
        and v2 == "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2_DEGRADED"
    )
