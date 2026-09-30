"""Fail-closed customer business identity semantics for Telchi analytics.

The module is intentionally pure and performs no I/O.  A customer type is only
assigned from an explicit, provenance-bearing assertion; names and activity
volume are never classifiers.  Unknown CardCodes therefore stay out of
commercial-customer rankings.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

COMMERCIAL_CUSTOMER = "COMMERCIAL_CUSTOMER"
GENERIC_CUSTOMER = "GENERIC_CUSTOMER"
INTERNAL_ACCOUNT = "INTERNAL_ACCOUNT"
FISCAL_TECHNICAL_ACCOUNT = "FISCAL_TECHNICAL_ACCOUNT"
OTHER_NON_COMMERCIAL = "OTHER_NON_COMMERCIAL"
UNKNOWN = "UNKNOWN"

TAXONOMY = (
    COMMERCIAL_CUSTOMER,
    GENERIC_CUSTOMER,
    INTERNAL_ACCOUNT,
    FISCAL_TECHNICAL_ACCOUNT,
    OTHER_NON_COMMERCIAL,
    UNKNOWN,
)

NON_COMMERCIAL_TYPES = frozenset(
    {GENERIC_CUSTOMER, INTERNAL_ACCOUNT, FISCAL_TECHNICAL_ACCOUNT, OTHER_NON_COMMERCIAL}
)


@dataclass(frozen=True)
class CustomerAssertion:
    customer_business_type: str
    source: str
    basis: str
    confidence: float = 1.0
    status: str = "VALIDATED"

    def __post_init__(self) -> None:
        if self.customer_business_type not in TAXONOMY or self.customer_business_type == UNKNOWN:
            raise ValueError("an explicit assertion must use a known non-UNKNOWN type")
        if not self.source or not self.basis:
            raise ValueError("classification provenance is mandatory")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class CustomerClassification:
    card_code: str
    card_name: str
    customer_business_type: str
    classification_status: str
    classification_source: str
    classification_basis: str
    classification_confidence: float


@dataclass(frozen=True)
class RawMaterialSale:
    source_system: str
    document_type: str
    doc_entry: str
    card_code: str
    doc_date: date
    item_code: str
    customer_business_type: str
    canceled: bool = False

    @property
    def document_key(self) -> tuple[str, str, str]:
        return self.source_system, self.document_type, self.doc_entry


def classify_customer(
    card_code: str,
    card_name: str,
    assertions: Mapping[str, CustomerAssertion],
) -> CustomerClassification:
    """Classify only from an exact CardCode assertion; otherwise return UNKNOWN."""
    assertion = assertions.get(card_code)
    if assertion is None:
        return CustomerClassification(
            card_code=card_code,
            card_name=card_name,
            customer_business_type=UNKNOWN,
            classification_status="UNKNOWN",
            classification_source="NO_EXPLICIT_EVIDENCE",
            classification_basis="No validated CardCode-level assertion is available",
            classification_confidence=0.0,
        )
    return CustomerClassification(
        card_code=card_code,
        card_name=card_name,
        customer_business_type=assertion.customer_business_type,
        classification_status=assertion.status,
        classification_source=assertion.source,
        classification_basis=assertion.basis,
        classification_confidence=assertion.confidence,
    )


def _rank(lines: Iterable[RawMaterialSale]) -> list[dict[str, object]]:
    documents: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    days: dict[str, set[date]] = defaultdict(set)
    skus: dict[str, set[str]] = defaultdict(set)
    first: dict[str, date] = {}
    last: dict[str, date] = {}
    for line in lines:
        if line.canceled or line.document_type != "SALES":
            continue
        documents[line.card_code].add(line.document_key)
        days[line.card_code].add(line.doc_date)
        skus[line.card_code].add(line.item_code)
        first[line.card_code] = min(first.get(line.card_code, line.doc_date), line.doc_date)
        last[line.card_code] = max(last.get(line.card_code, line.doc_date), line.doc_date)
    ordered = sorted(documents, key=lambda card: (-len(documents[card]), card))
    result: list[dict[str, object]] = []
    previous: int | None = None
    rank = 0
    for position, card_code in enumerate(ordered, 1):
        count = len(documents[card_code])
        if count != previous:
            rank, previous = position, count
        result.append(
            {
                "rank": rank,
                "card_code": card_code,
                "purchase_documents": count,
                "purchase_days": len(days[card_code]),
                "first_purchase": first[card_code],
                "last_purchase": last[card_code],
                "distinct_raw_material_skus": len(skus[card_code]),
            }
        )
    return result


def rank_all_cardcodes(lines: Iterable[RawMaterialSale]) -> list[dict[str, object]]:
    """Rank all CardCodes; this output must not be labelled a commercial ranking."""
    return _rank(lines)


def rank_commercial_customers(lines: Iterable[RawMaterialSale]) -> list[dict[str, object]]:
    """Rank only explicitly classified COMMERCIAL_CUSTOMER CardCodes."""
    return _rank(line for line in lines if line.customer_business_type == COMMERCIAL_CUSTOMER)


def unknown_could_change_winner(
    commercial_document_counts: Mapping[str, int],
    unknown_document_counts: Mapping[str, int],
) -> bool:
    """Return the conservative fail-closed sensitivity result."""
    if not unknown_document_counts:
        return False
    if not commercial_document_counts:
        return any(count > 0 for count in unknown_document_counts.values())
    winner = max(commercial_document_counts.values())
    return any(count >= winner for count in unknown_document_counts.values())


def generic_raw_material_control_status(customer_business_type: str) -> str:
    """Detection-only control: no policy or legal conclusion is implied."""
    return "REVIEW_REQUIRED" if customer_business_type == GENERIC_CUSTOMER else "NOT_APPLICABLE"


__all__ = [
    "COMMERCIAL_CUSTOMER",
    "GENERIC_CUSTOMER",
    "INTERNAL_ACCOUNT",
    "FISCAL_TECHNICAL_ACCOUNT",
    "OTHER_NON_COMMERCIAL",
    "UNKNOWN",
    "TAXONOMY",
    "NON_COMMERCIAL_TYPES",
    "CustomerAssertion",
    "CustomerClassification",
    "RawMaterialSale",
    "classify_customer",
    "rank_all_cardcodes",
    "rank_commercial_customers",
    "unknown_could_change_winner",
    "generic_raw_material_control_status",
]
