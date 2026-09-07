"""Atomic contracts: relations, source, production."""
from __future__ import annotations

from dataclasses import dataclass

from modules.telchi.investigation.atomic.contracts.event_envelope import (
    Field, f, CONFIRMED, CANDIDATE,
)

# ---- DOCUMENT_RELATION (§11) -----------------------------------------------------------
RELATION_TYPES_CANDIDATE = frozenset(
    {
        "BASED_ON", "GENERATES", "CONVERTED_TO", "DELIVERED_BY", "BILLED_BY",
        "PAID_BY", "APPLIED_TO", "RECONCILED_BY", "CANCELED_BY", "REVERSED_BY",
        "REPLACED_BY", "RETURNED_BY", "FULFILLED_BY",
    }
)

MATCH_METHODS = frozenset(
    {
        "DIRECT_REFERENCE", "SAP_BASEENTRY", "EXTERNAL_ID", "FOLIO",
        "INTEGRATION_ID", "EXACT_DOCUMENT_ID", "BATCH_REFERENCE",
        "AMOUNT_TIME_MATCH", "ITEM_QUANTITY_MATCH", "INFERRED", "MANUAL_CONFIRMED",
    }
)

# SAP SrcObjTyp -> logical object type (confirmed from doc/ITR1 investigation).
SRC_OBJECT_TYPES: dict[int, str] = {
    13: "AR_INVOICE",
    14: "AR_CREDIT_NOTE",
    16: "AR_RETURN",        # DEC-012 (not purchase invoice)
    18: "AP_INVOICE",
    20: "JOURNAL_ENTRY",
    24: "INCOMING_PAYMENT",
    25: "OUTGOING_PAYMENT",
    30: "JOURNAL_ENTRY",
    46: "JOURNAL_ENTRY",
}


@dataclass(frozen=True)
class DocumentRelation:
    relation_type: str
    from_system: str
    from_object_type: str
    from_document_id: int
    from_line_id: int | None
    to_system: str
    to_object_type: str
    to_document_id: int
    to_line_id: int | None
    match_method: str
    confidence: float
    evidence: str

    def __post_init__(self) -> None:
        if self.relation_type not in RELATION_TYPES_CANDIDATE:
            raise ValueError(f"unknown relation_type {self.relation_type}")
        if self.match_method not in MATCH_METHODS:
            raise ValueError(f"unknown match_method {self.match_method}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0,1]")


# ---- SOURCE_TRANSACTION contract (§78, §44) --------------------------------------------
SOURCE_TRANSACTION_FIELDS: dict[str, str] = {
    "channel": "str",
    "source_system": "str",
    "source_transaction_id": "str",
    "external_folio": "str",
    "branch": "str",
    "source_object_type": "str",
    "source_document_id": "int",
    "business_date": "date",
    "cash_settlement_date": "date",
    "amount": "float",
    "status": "str",
}

# ---- CROSS_SYSTEM_LINK (§78) -----------------------------------------------------------
CROSS_SYSTEM_LINK_FIELDS: dict[str, str] = {
    "channel": "str",
    "source_system": "str",
    "source_transaction_id": "str",
    "external_folio": "str",
    "sap_object_type": "str",
    "sap_document_id": "int",
    "match_method": "str",
    "confidence": "float",
    "evidence": "str",
}

# ---- CHANNEL_OPERATION_RULE (§27) ------------------------------------------------------
# Initially UNKNOWN / DISCOVERY_REQUIRED by policy — never fabricate rules.
CHANNEL_DISCOVERY: dict[str, dict] = {
    "retail_one": {
        "status": "PARTIAL_TRACEABILITY",
        "sale_grain": "ONE_INVOICE_PER_FOLIO (CANDIDATE)",
        "cash_behavior": "UNKNOWN",
        "cash_max_delay": None,
        "stock_behavior": "UNKNOWN",
        "sap_posting": "INVOICE_PER_FOLIO (CANDIDATE)",
        "integration_mode": "FOLIO_UDF_MARKED",
        "document_type": "AR_INVOICE",
        "warehouse": "UNKNOWN",
        "evidence": {
            "udf_flag": "U_SO1_01RETAILONE in {Y,N}",
            "udf_folio": "U_SO1_01FOLIORETAIL1 (ticket folio)",
            "share_2026_07": "Y=89.5% / N=10.5% of sampled invoices (n=50k)",
            "distinct_folios_2026_07": 58778,
        },
    },
    "dms": {
        "status": "PARTIAL_TRACEABILITY",
        "sale_grain": "UNKNOWN",
        "cash_behavior": "UNKNOWN",
        "cash_max_delay": None,
        "stock_behavior": "UNKNOWN",
        "sap_posting": "UNKNOWN",
        "integration_mode": "ORIGIN_UDF_MARKED",
        "document_type": "AR_INVOICE",
        "warehouse": "UNKNOWN",
        "evidence": {
            "udf_origin": "U_ORIGIN in {SAP, DMS}",
            "udf_state": "U_DMS_STATE in {A, V}",
            "share_recent": "DMS ~8% of sampled invoices (n=200k, 2026-01+)",
        },
    },
    "sap": {
        "status": "NATIVE",
        "sale_grain": "INVOICE_LINE",
        "cash_behavior": "UNKNOWN",
        "stock_behavior": "UNKNOWN",
        "integration_mode": "NATIVE",
        "document_type": "AR_INVOICE",
    },
}

# ---- BOM / PRODUCTION (§28-30) ---------------------------------------------------------
BOM_HEADER_FIELDS: dict[str, Field] = {
    "Code": f("Code", "OITT", CONFIRMED, "BOM item / finished good"),
    "TreeType": f("TreeType", "OITT", CONFIRMED),
    "Quantity": f("Qauntity", "OITT", CONFIRMED, "SAP field is 'Qauntity'"),
    "Name": f("Name", "OITT", CONFIRMED),
    "ToWH": f("ToWH", "OITT", CONFIRMED),
    "CreateDate": f("CreateDate", "OITT", CONFIRMED),
    "UpdateDate": f("UpdateDate", "OITT", CONFIRMED),
}
BOM_LINE_FIELDS: dict[str, Field] = {
    "Father": f("Father", "ITT1", CONFIRMED, "parent BOM code"),
    "ChildNum": f("ChildNum", "ITT1", CONFIRMED),
    "Code": f("Code", "ITT1", CONFIRMED, "component item code"),
    "Quantity": f("Quantity", "ITT1", CONFIRMED, "qty per unit"),
    "Warehouse": f("Warehouse", "ITT1", CONFIRMED),
    "Price": f("Price", "ITT1", CONFIRMED),
    "Uom": f("Uom", "ITT1", CONFIRMED),
    "ItemName": f("ItemName", "ITT1", CONFIRMED, "component name"),
}
PRODUCTION_ORDER_FIELDS: dict[str, Field] = {
    "DocEntry": f("DocEntry", "OWOR", CONFIRMED),
    "DocNum": f("DocNum", "OWOR", CONFIRMED),
    "ItemCode": f("ItemCode", "OWOR", CONFIRMED),
    "Status": f("Status", "OWOR", CONFIRMED),
    "Type": f("Type", "OWOR", CONFIRMED),
    "PlannedQty": f("PlannedQty", "OWOR", CONFIRMED),
    "CmpltQty": f("CmpltQty", "OWOR", CONFIRMED),
    "Warehouse": f("Warehouse", "OWOR", CONFIRMED),
    "StartDate": f("StartDate", "OWOR", CONFIRMED),
}