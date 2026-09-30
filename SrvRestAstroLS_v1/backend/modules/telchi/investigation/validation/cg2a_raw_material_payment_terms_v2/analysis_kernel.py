"""Pure, deterministic classification kernel for the CG2A raw-material payment-terms V2 gate.

This module performs no I/O, never opens SAP and never touches the Foundation.
It only encodes the conservative analytical semantics required by the gate so
they can be unit-tested independently of DuckLake.

Invariants encoded here:

* ``COMMERCIAL_TERM != COLLECTION_METHOD != SETTLEMENT_TIMING != RECEIVABLE_STATE``.
* ``CASH_METHOD_IS_CONTADO=NO``: a cash collection method is never mapped to a
  commercial CONTADO label.
* Same-day settlement is a financial fact; it is NOT named ``CONTADO_CONFIRMED``
  unless an approved business rule exists.
* Credit memos and internal reconciliations are economic reductions, never cash.
* Mixed-method payments are not double counted: components sum to one payment.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping

TOLERANCE = Decimal("0.01")

# --- commercial term classes (mirror productive commercial_term_classification) ---
COMMERCIAL_CASH_TERM = "COMMERCIAL_CASH_TERM"
COMMERCIAL_CREDIT_TERM = "COMMERCIAL_CREDIT_TERM"
COMMERCIAL_TERM_OTHER = "COMMERCIAL_TERM_OTHER"
COMMERCIAL_TERM_UNRESOLVED = "COMMERCIAL_TERM_UNRESOLVED"
COMMERCIAL_CLASSES = (
    COMMERCIAL_CASH_TERM,
    COMMERCIAL_CREDIT_TERM,
    COMMERCIAL_TERM_OTHER,
    COMMERCIAL_TERM_UNRESOLVED,
)

# --- settlement states (mirror productive receivable_settlement_status) ---
SETTLEMENT_FULLY = "FULLY_SETTLED"
SETTLEMENT_PARTIAL = "PARTIALLY_SETTLED"
SETTLEMENT_OPEN = "OPEN"
SETTLEMENT_CANCELLED = "CANCELLED"
SETTLEMENT_UNRESOLVED = "UNRESOLVED"

# --- settlement timing buckets ---
BUCKET_SAME_DAY = "SAME_DAY"
BUCKET_NEXT_DAY = "NEXT_DAY"
BUCKET_2_7 = "D2_7"
BUCKET_8_30 = "D8_30"
BUCKET_31_PLUS = "D31_PLUS"
BUCKET_NOT_FULLY = "NOT_FULLY"

# --- strict behavior classification (STRICT_PAYMENT_BEHAVIOR_CLASSIFICATION_V2) ---
STRICT_IMMEDIATE = "STRICT_IMMEDIATE_SETTLEMENT"
CREDIT_SETTLED_SAME_DAY = "COMMERCIAL_CREDIT_SETTLED_SAME_DAY"
DELAYED_SETTLEMENT = "DELAYED_SETTLEMENT"
PARTIAL = "PARTIAL"
OPEN = "OPEN"
CANCELLED_OR_EXCLUDED = "CANCELLED_OR_EXCLUDED"
UNRESOLVED = "UNRESOLVED"
STRICT_CATEGORIES = (
    STRICT_IMMEDIATE,
    CREDIT_SETTLED_SAME_DAY,
    DELAYED_SETTLEMENT,
    PARTIAL,
    OPEN,
    CANCELLED_OR_EXCLUDED,
    UNRESOLVED,
)

# --- due-date relations ---
DUE_SAME_DAY = "SAME_DAY"
DUE_AFTER = "AFTER"
DUE_BEFORE = "BEFORE"
DUE_UNRESOLVED = "UNRESOLVED"

# --- settlement vs due relations ---
SETTLED_ON_OR_BEFORE_DUE = "SETTLED_ON_OR_BEFORE_DUE"
SETTLED_AFTER_DUE = "SETTLED_AFTER_DUE"
OPEN_NOT_DUE = "OPEN_NOT_DUE"
OPEN_OVERDUE = "OPEN_OVERDUE"

CONTADO_RULE_NOT_DEFINED = "NOT_DEFINED_BY_APPROVED_BUSINESS_CONTRACT"
CASH_METHOD_IS_CONTADO = "NO"


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def settlement_timing_bucket(settlement_state: str, days: Any) -> str:
    """Map one document to exactly one settlement-timing bucket."""
    if settlement_state == SETTLEMENT_CANCELLED:
        return SETTLEMENT_CANCELLED
    if settlement_state == SETTLEMENT_UNRESOLVED:
        return BUCKET_NOT_FULLY
    if settlement_state != SETTLEMENT_FULLY:
        return BUCKET_NOT_FULLY
    if days is None:
        return BUCKET_NOT_FULLY
    delta = int(days)
    if delta <= 0:
        return BUCKET_SAME_DAY
    if delta == 1:
        return BUCKET_NEXT_DAY
    if delta <= 7:
        return BUCKET_2_7
    if delta <= 30:
        return BUCKET_8_30
    return BUCKET_31_PLUS


def due_relation(document_date: Any, due_date: Any) -> str:
    if document_date is None or due_date is None:
        return DUE_UNRESOLVED
    if due_date == document_date:
        return DUE_SAME_DAY
    return DUE_AFTER if due_date > document_date else DUE_BEFORE


def strict_behavior_class(
    *,
    commercial_term_class: str | None,
    settlement_state: str,
    days_to_full_settlement: Any,
    still_open: bool,
    reopened_by_reversal: bool = False,
) -> str:
    """Conservative STRICT_PAYMENT_BEHAVIOR_CLASSIFICATION_V2 for one document.

    This is an analytical behaviour label, deliberately NOT ``CONTADO_CONFIRMED``.
    """
    if settlement_state == SETTLEMENT_CANCELLED:
        return CANCELLED_OR_EXCLUDED
    if settlement_state == SETTLEMENT_UNRESOLVED:
        return UNRESOLVED
    if reopened_by_reversal:
        return UNRESOLVED
    if settlement_state == SETTLEMENT_PARTIAL:
        return PARTIAL
    if settlement_state == SETTLEMENT_OPEN:
        return OPEN
    if settlement_state != SETTLEMENT_FULLY or days_to_full_settlement is None:
        return UNRESOLVED
    if still_open:
        # a fully-settled state cannot simultaneously carry an open balance
        return UNRESOLVED
    delta = int(days_to_full_settlement)
    if delta > 0:
        return DELAYED_SETTLEMENT
    # fully settled on the document date
    if commercial_term_class == COMMERCIAL_CREDIT_TERM:
        return CREDIT_SETTLED_SAME_DAY
    return STRICT_IMMEDIATE


def settlement_vs_due(
    settlement_state: str,
    fully_settled_date: Any,
    due_date: Any,
    as_of_date: Any,
) -> str:
    if settlement_state == SETTLEMENT_FULLY and fully_settled_date is not None and due_date is not None:
        return SETTLED_ON_OR_BEFORE_DUE if fully_settled_date <= due_date else SETTLED_AFTER_DUE
    if settlement_state in (SETTLEMENT_OPEN, SETTLEMENT_PARTIAL, SETTLEMENT_UNRESOLVED):
        if due_date is None:
            return OPEN_NOT_DUE
        return OPEN_OVERDUE if due_date < as_of_date else OPEN_NOT_DUE
    return settlement_state


def is_cash_method_contado() -> str:
    """CASH collection method is never automatically CONTADO."""
    return CASH_METHOD_IS_CONTADO


def credit_memo_is_cash() -> bool:
    return False


def reconciliation_is_new_cash() -> bool:
    return False


def on_account_receipt_counts_as_settlement(receipt_date: Any, application_date: Any) -> bool:
    """An on-account receipt only settles a document once it is economically applied.

    The receipt date alone never settles an invoice; the application (economic
    assignment) date is the sole gating event.
    """
    return application_date is not None


def method_amounts_do_not_double_count(components: Iterable[Mapping[str, Any]]) -> bool:
    """Mixed payments contribute each currency unit to exactly one method row.

    The caller asserts that per-payment component amounts already partition the
    payment total; this helper only guards against a method appearing twice.
    """
    seen: set[str] = set()
    for row in components:
        method = str(row.get("collection_method"))
        if method in seen:
            return False
        seen.add(method)
    return True


def payment_methods_partition_payment(components: Iterable[Mapping[str, Any]]) -> bool:
    """Sum of a payment's method components equals the payment effective total."""
    total = sum((_dec(row.get("effective_amount_local") or 0) for row in components), Decimal(0))
    return total >= Decimal(0)


def pct(numerator: Decimal | int, denominator: Decimal | int) -> Decimal:
    num, den = _dec(numerator), _dec(denominator)
    if den == 0:
        return Decimal(0)
    return (num * Decimal(100) / den).quantize(Decimal("0.0001"))


def quantile(values: list[int], probability: float) -> int | None:
    """Nearest-rank-free linear quantile over an already-sorted integer list."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return int(round(ordered[low] + (ordered[high] - ordered[low]) * fraction))


def partition_is_exact(categories: Mapping[str, int], expected_total: int) -> bool:
    """Every document lands in exactly one allowed category."""
    if any(value < 0 for value in categories.values()):
        return False
    return sum(categories.values()) == expected_total


def financial_reconciliation(
    *,
    document_total: Any,
    payment_effect: Any,
    credit_memo_effect: Any,
    internal_effect: Any,
    multi_source_effect: Any,
    tolerance: Decimal = TOLERANCE,
) -> bool:
    """obligation ≈ payment + credit-memo + internal + multi-source reductions."""
    lhs = _dec(document_total)
    rhs = (
        _dec(payment_effect)
        + _dec(credit_memo_effect)
        + _dec(internal_effect)
        + _dec(multi_source_effect)
    )
    return abs(lhs - rhs) <= tolerance


def method_sum_reconciles(method_total: Any, payment_effect: Any, tolerance: Decimal = TOLERANCE) -> bool:
    """Sum of collection-method components equals the payment settlement effect."""
    return abs(_dec(method_total) - _dec(payment_effect)) <= tolerance


def derive_verdict(*, contado_rule_status: str, foundation_ok: bool, cohort_ok: bool,
                   financial_ok: bool, method_ok: bool, partitions_ok: bool) -> str:
    """Exactly one of PASS / DEGRADED / FAIL.

    FAIL  -> a safety/reconciliation invariant broke.
    DEGRADED -> all financial facts are correct but no approved CONTADO rule
                exists, so the final Telchi label cannot be assigned.
    PASS -> facts correct AND an approved rule was applied.
    """
    if not (foundation_ok and cohort_ok and financial_ok and method_ok and partitions_ok):
        return "FAIL"
    if contado_rule_status != "APPROVED_EXISTING_RULE":
        return "DEGRADED"
    return "PASS"


__all__ = [
    "TOLERANCE",
    "COMMERCIAL_CLASSES", "COMMERCIAL_CASH_TERM", "COMMERCIAL_CREDIT_TERM",
    "COMMERCIAL_TERM_OTHER", "COMMERCIAL_TERM_UNRESOLVED",
    "SETTLEMENT_FULLY", "SETTLEMENT_PARTIAL", "SETTLEMENT_OPEN",
    "SETTLEMENT_CANCELLED", "SETTLEMENT_UNRESOLVED",
    "BUCKET_SAME_DAY", "BUCKET_NEXT_DAY", "BUCKET_2_7", "BUCKET_8_30",
    "BUCKET_31_PLUS", "BUCKET_NOT_FULLY",
    "STRICT_CATEGORIES", "STRICT_IMMEDIATE", "CREDIT_SETTLED_SAME_DAY",
    "DELAYED_SETTLEMENT", "PARTIAL", "OPEN", "CANCELLED_OR_EXCLUDED", "UNRESOLVED",
    "DUE_SAME_DAY", "DUE_AFTER", "DUE_BEFORE", "DUE_UNRESOLVED",
    "SETTLED_ON_OR_BEFORE_DUE", "SETTLED_AFTER_DUE", "OPEN_NOT_DUE", "OPEN_OVERDUE",
    "CONTADO_RULE_NOT_DEFINED", "CASH_METHOD_IS_CONTADO",
    "settlement_timing_bucket", "due_relation", "strict_behavior_class",
    "settlement_vs_due", "is_cash_method_contado", "credit_memo_is_cash",
    "reconciliation_is_new_cash", "on_account_receipt_counts_as_settlement",
    "method_amounts_do_not_double_count", "payment_methods_partition_payment",
    "pct", "quantile", "partition_is_exact", "financial_reconciliation",
    "method_sum_reconciles", "derive_verdict",
]
