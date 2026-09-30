"""Deterministic Telchi product-to-business-type classification.

This is a pure semantic kernel: it performs no I/O and never opens SAP.  Raw
material requires combined item-group and BOM evidence; being a BOM leaf alone
is deliberately insufficient.  Name patterns can support packaging, but never
produce an exact classification on their own.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

RAW_MATERIAL = "RAW_MATERIAL"
FRACTIONATED_PRODUCT = "FRACTIONATED_PRODUCT"
PACKAGING = "PACKAGING"
LAB_FINISHED_PRODUCT = "LAB_FINISHED_PRODUCT"
OTHER_INPUT = "OTHER_INPUT"
SEMI_FINISHED = "SEMI_FINISHED"
TRADED_PRODUCT = "TRADED_PRODUCT"
SERVICE = "SERVICE"
OTHER = "OTHER"
UNKNOWN = "UNKNOWN"

TAXONOMY = (
    RAW_MATERIAL,
    FRACTIONATED_PRODUCT,
    PACKAGING,
    LAB_FINISHED_PRODUCT,
    OTHER_INPUT,
    SEMI_FINISHED,
    TRADED_PRODUCT,
    SERVICE,
    OTHER,
    UNKNOWN,
)

FRACTIONATED_GROUPS = frozenset({125, 126, 127, 128})
RAW_INPUT_GROUPS = frozenset({117, 123, 129, 131, 133})
PACKAGING_GROUPS = frozenset({130})
SERVICE_GROUPS = frozenset({141, 143})
OTHER_GROUPS = frozenset({119, 120, 140, 144})
COMMERCIAL_GROUPS = frozenset(set(range(100, 119)) | {121, 132, 134, 135, 136, 137, 138, 139, 142})

PACKAGING_RE = re.compile(
    r"FRASCO|TAPA|ETIQUETA|CAJA|ENVASE|BOLSA|PREFORM|CONTRA|GOTERO|SPRAY|"
    r"PULVERIZ|BOMBA|PRECINTA|PRECINTO|DOSIFIC|BIDON|TURRIL(?!\s*x)|BOTELLA|"
    r"CINTA|STICKER|TAPON|AMPOLLA|SACHET|BLISTER|POTE",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProductFacts:
    item_code: str
    item_name: str
    item_group_code: int | None
    item_group_name: str | None
    inventory_item: bool
    sell_item: bool
    purchase_item: bool
    active: bool
    is_bom_parent: bool = False
    is_bom_component: bool = False
    is_produced: bool = False


@dataclass(frozen=True)
class Classification:
    product_business_type: str
    rule_id: str
    basis: str
    source: str
    confidence: float
    evidence: str
    status: str
    conflict: bool = False
    name_only: bool = False


def _result(
    value: str,
    rule_id: str,
    basis: str,
    confidence: float,
    evidence: str,
    status: str = "VALIDATED",
    *,
    conflict: bool = False,
    name_only: bool = False,
) -> Classification:
    return Classification(
        product_business_type=value,
        rule_id=rule_id,
        basis=basis,
        source="TELCHI_PRODUCT_BUSINESS_CLASSIFICATION_V1",
        confidence=confidence,
        evidence=evidence,
        status=status,
        conflict=conflict,
        name_only=name_only,
    )


@dataclass(frozen=True)
class PurchaseLine:
    source_system: str
    document_type: str
    doc_entry: str
    card_code: str
    doc_date: date
    item_code: str
    product_business_type: str
    canceled: bool = False


def rank_purchase_frequency(lines: Iterable[PurchaseLine]) -> list[dict[str, object]]:
    """Rank RAW_MATERIAL customers by distinct sales-document occasions."""
    documents: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    days: dict[str, set[date]] = defaultdict(set)
    skus: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if line.canceled or line.document_type != "SALES" or line.product_business_type != RAW_MATERIAL:
            continue
        documents[line.card_code].add((line.source_system, line.document_type, line.doc_entry))
        days[line.card_code].add(line.doc_date)
        skus[line.card_code].add(line.item_code)
    ordered = sorted(documents, key=lambda card: (-len(documents[card]), card))
    result: list[dict[str, object]] = []
    previous_count: int | None = None
    rank = 0
    for position, card in enumerate(ordered, 1):
        count = len(documents[card])
        if count != previous_count:
            rank = position
            previous_count = count
        result.append({
            "rank": rank, "card_code": card, "purchase_documents": count,
            "purchase_days": len(days[card]), "distinct_raw_material_skus": len(skus[card]),
        })
    return result


def unknown_items_can_change_winner(
    raw_documents: Mapping[str, int], unknown_documents: Mapping[str, int]
) -> bool:
    """Conservative upper-bound sensitivity for sold UNKNOWN items."""
    if not raw_documents:
        return any(unknown_documents.values())
    winner = max(raw_documents.values())
    winners = {card for card, count in raw_documents.items() if count == winner}
    return any(
        card not in winners and raw_documents.get(card, 0) + unknown >= winner
        for card, unknown in unknown_documents.items()
    )


def classify_product(facts: ProductFacts) -> Classification:
    """Classify one item using deterministic, high-to-low authority rules."""
    group = facts.item_group_code
    packaging_name = bool(PACKAGING_RE.search(facts.item_name or ""))

    # Explicit item-group semantics are master-data authority.  They precede
    # production/BOM position so a manufactured container remains packaging.
    if group in PACKAGING_GROUPS:
        return _result(PACKAGING, "PBT-001", "ITEM_GROUP", 1.0, f"ItmsGrpCod={group}: {facts.item_group_name}")
    if group in FRACTIONATED_GROUPS and (facts.is_produced or facts.is_bom_parent):
        return _result(
            FRACTIONATED_PRODUCT,
            "PBT-002",
            "COMBINED",
            1.0,
            f"explicit FRACCIONADO group {group}: {facts.item_group_name}; produced/BOM-parent evidence",
        )

    # Produced/BOM-parent position distinguishes laboratory finished and
    # intermediate products without inferring from the display name.
    if facts.is_produced or facts.is_bom_parent:
        if facts.sell_item:
            return _result(
                LAB_FINISHED_PRODUCT,
                "PBT-003",
                "COMBINED",
                0.95,
                f"produced={facts.is_produced}; bom_parent={facts.is_bom_parent}; SellItem=Y",
            )
        return _result(
            SEMI_FINISHED,
            "PBT-004",
            "STRUCTURAL",
            0.95,
            f"produced={facts.is_produced}; bom_parent={facts.is_bom_parent}; SellItem=N",
        )

    # Packaging text is only supporting evidence.  Combined with BOM position
    # it is supported, never EXACT; by itself it remains provisional.
    if packaging_name and facts.is_bom_component:
        return _result(
            PACKAGING,
            "PBT-005",
            "COMBINED",
            0.85,
            f"BOM component plus packaging term in ItemName={facts.item_name!r}",
            "SUPPORTED",
        )

    # Crucial invariant: BOM leaf alone is not raw material.  A raw-material
    # result additionally requires an input-oriented item group.
    if facts.is_bom_component and group in (RAW_INPUT_GROUPS | FRACTIONATED_GROUPS):
        return _result(
            RAW_MATERIAL,
            "PBT-006",
            "COMBINED",
            0.95,
            f"BOM component and input/bulk group {group}: {facts.item_group_name}",
        )

    # A residual item in an explicit FRACCIONADO group remains fractionated;
    # the earlier combined rule prevents bulk BOM inputs in that group from
    # being mislabeled as the commercial fractionated presentation.
    if group in FRACTIONATED_GROUPS:
        return _result(
            FRACTIONATED_PRODUCT,
            "PBT-002B",
            "ITEM_GROUP",
            0.9,
            f"ItmsGrpCod={group}: {facts.item_group_name}; no BOM-component evidence",
            "SUPPORTED",
        )

    if packaging_name:
        return _result(
            PACKAGING,
            "PBT-007",
            "NAME_BASED",
            0.65,
            f"packaging term in ItemName={facts.item_name!r}; no structural corroboration",
            "PROVISIONAL",
            name_only=True,
        )
    if group in RAW_INPUT_GROUPS:
        return _result(
            OTHER_INPUT,
            "PBT-008",
            "ITEM_GROUP",
            0.9,
            f"input group {group}: {facts.item_group_name}; no BOM raw-material evidence",
            "SUPPORTED",
        )
    if group in SERVICE_GROUPS:
        return _result(SERVICE, "PBT-009", "ITEM_GROUP", 1.0, f"service group {group}: {facts.item_group_name}")
    if group in OTHER_GROUPS:
        return _result(OTHER, "PBT-010", "ITEM_GROUP", 0.9, f"non-product group {group}: {facts.item_group_name}", "SUPPORTED")
    if facts.sell_item and (facts.purchase_item or group in COMMERCIAL_GROUPS):
        return _result(
            TRADED_PRODUCT,
            "PBT-011",
            "COMBINED",
            0.9,
            f"SellItem=Y; PrchseItem={facts.purchase_item}; commercial group={group}",
            "SUPPORTED",
        )
    return _result(
        UNKNOWN,
        "PBT-999",
        "UNKNOWN",
        0.0,
        "insufficient structural/master-data evidence",
        "UNKNOWN",
    )


__all__ = [
    "Classification",
    "ProductFacts",
    "PurchaseLine",
    "TAXONOMY",
    "classify_product",
    "rank_purchase_frequency",
    "unknown_items_can_change_winner",
    "RAW_MATERIAL",
    "FRACTIONATED_PRODUCT",
    "PACKAGING",
    "LAB_FINISHED_PRODUCT",
    "OTHER_INPUT",
    "SEMI_FINISHED",
    "TRADED_PRODUCT",
    "SERVICE",
    "OTHER",
    "UNKNOWN",
]
