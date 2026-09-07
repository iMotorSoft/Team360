"""Atomic event contracts (TELCHI spec §9, §10, §43).

Base EVENT_ENVELOPE is the minimum common envelope for facts from any system.
Domain-specific key maps enumerate only CONFIRMED SAP columns (inspected on HANA).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Field confidence levels (§7) -------------------------------------------------
CONFIRMED = "CONFIRMED"
LEGACY_REFERENCED = "LEGACY_REFERENCED"
CANDIDATE = "CANDIDATE"


@dataclass(frozen=True)
class Field:
    name: str
    confidence: str
    source: str  # table or provenance
    note: str = ""


def f(name: str, source: str, confidence: str = CONFIRMED, note: str = "") -> Field:
    return Field(name=name, confidence=confidence, source=source, note=note)


# ---- Base event envelope (§9) ----------------------------------------------------
# These are contract keys (logical), not raw SAP columns. Mapping to SAP goes in
# domain envelope tables below. base_event_envelope is the COMMON MINIMUM.
BASE_EVENT_ENVELOPE: dict[str, str] = {
    # identity
    "source_system": "str",
    "source_object_type": "str",
    "source_document_id": "int",
    "source_document_number": "str",
    "source_line_id": "int",
    # business time
    "business_event_type": "str",
    "business_date": "date",
    "posting_date": "date",
    "event_at": "timestamp",
    "created_at": "date",
    "updated_at": "date",
    "ingested_at": "timestamp",
    # dims
    "customer_id": "str",
    "seller_id": "int",
    "item_id": "str",
    "branch_id": "str",
    "warehouse_id": "str",
    # amounts / quantity
    "currency": "str",
    "quantity": "float",
    "uom": "str",
    "amount_document": "float",
    "amount_local": "float",
    # state
    "status": "str",
    "cancelled": "bool",
    # provenance
    "user_id": "int",
    "transaction_id": "int",
    "ingestion_batch_id": "str",
    "source_hash": "str",
}

# ---- SALE header (P0): OINV confirmed fields (§14) -------------------------------------------
SALE_HEADER: dict[str, Field] = {
    "DocEntry": f("DocEntry", "OINV", CONFIRMED, "PK invoice header"),
    "ObjType": f("ObjType", "OINV", CONFIRMED),
    "DocNum": f("DocNum", "OINV", CONFIRMED),
    "TransId": f("TransId", "OINV", CONFIRMED),
    "CardCode": f("CardCode", "OINV", CONFIRMED),
    "SlpCode": f("SlpCode", "OINV", CONFIRMED),
    "DocDate": f("DocDate", "OINV", CONFIRMED, "business date"),
    "TaxDate": f("TaxDate", "OINV", CONFIRMED),
    "DocDueDate": f("DocDueDate", "OINV", CONFIRMED),
    "DocTotal": f("DocTotal", "OINV", CONFIRMED),
    "DocCur": f("DocCur", "OINV", CONFIRMED),
    "PaidToDate": f("PaidToDate", "OINV", CONFIRMED, "historical payments"),
    "CANCELED": f("CANCELED", "OINV", CONFIRMED, "N/Y/C"),
    "DocStatus": f("DocStatus", "OINV", CONFIRMED, "O/C"),
    "CreateDate": f("CreateDate", "OINV", CONFIRMED),
    "UpdateDate": f("UpdateDate", "OINV", CONFIRMED, "cancellation/update date"),
    "UpdateTS": f("UpdateTS", "OINV", CONFIRMED),
    "DocSubType": f("DocSubType", "OINV", CONFIRMED),
    "Series": f("Series", "OINV", CONFIRMED),
    "NumAtCard": f("NumAtCard", "OINV", CONFIRMED),
}

# SALE header UDFs that carry confirmed channel evidence (§24/25/26)
SALE_HEADER_UDF_CANDIDATE: dict[str, Field] = {
    "U_ORIGIN": f("U_ORIGIN", "OINV", CONFIRMED, "observed: SAP / DMS"),
    "U_TIPOVENTA": f("U_TIPOVENTA", "OINV", CONFIRMED, "observed: '0' only"),
    "U_DMS_STATE": f("U_DMS_STATE", "OINV", CONFIRMED, "observed: V/A"),
    "U_SO1_01RETAILONE": f("U_SO1_01RETAILONE", "OINV", CONFIRMED, "observed: Y/N"),
    "U_SO1_01FOLIORETAIL1": f("U_SO1_01FOLIORETAIL1", "OINV", CONFIRMED, "Retail One folio, observed"),
    "U_SO1_01SUCURSAL": f("U_SO1_01SUCURSAL", "OINV", CONFIRMED, "Retail One branch prefix"),
    "U_SO1_01PREFIJO": f("U_SO1_01PREFIJO", "OINV", CONFIRMED, "series prefix 231-234"),
    "U_SO1_01FOLIOIMPRESO": f("U_SO1_01FOLIOIMPRESO", "OINV", CANDIDATE),
}

# SALE line (§14): confirmed fields
SALE_LINE: dict[str, Field] = {
    "DocEntry": f("DocEntry", "INV1", CONFIRMED),
    "LineNum": f("LineNum", "INV1", CONFIRMED),
    "ItemCode": f("ItemCode", "INV1", CONFIRMED),
    "Quantity": f("Quantity", "INV1", CONFIRMED),
    "unitMsr": f("unitMsr", "INV1", CONFIRMED, "UOM"),
    "WhsCode": f("WhsCode", "INV1", CONFIRMED),
    "Price": f("Price", "INV1", CONFIRMED),
    "DiscPrcnt": f("DiscPrcnt", "INV1", CONFIRMED),
    "LineTotal": f("LineTotal", "INV1", CONFIRMED),
    "GTotal": f("GTotal", "INV1", CONFIRMED),
    "BaseType": f("BaseType", "INV1", CONFIRMED, "15=delivery, 23=quotation, 13=?"),
    "BaseEntry": f("BaseEntry", "INV1", CONFIRMED),
    "BaseLine": f("BaseLine", "INV1", CONFIRMED),
}

# Payment header (§17): confirmed ORCT columns including payment instruments
PAYMENT_HEADER: dict[str, Field] = {
    "DocEntry": f("DocEntry", "ORCT", CONFIRMED),
    "DocNum": f("DocNum", "ORCT", CONFIRMED),
    "CardCode": f("CardCode", "ORCT", CONFIRMED),
    "DocDate": f("DocDate", "ORCT", CONFIRMED),
    "DocTotal": f("DocTotal", "ORCT", CONFIRMED),
    "Canceled": f("Canceled", "ORCT", CONFIRMED, "note casing differs from OINV"),
    "DocCurr": f("DocCurr", "ORCT", CONFIRMED, "payment currency field (DEC-015)"),
    "TransId": f("TransId", "ORCT", CONFIRMED),
    # payment instrument decomposition (T04 evidence)
    "CashSum": f("CashSum", "ORCT", CONFIRMED, "cash amount"),
    "CheckSum": f("CheckSum", "ORCT", CONFIRMED, "check amount"),
    "TrsfrSum": f("TrsfrSum", "ORCT", CONFIRMED, "transfer amount"),
    "CreditSum": f("CreditSum", "ORCT", CONFIRMED, "credit card amount"),
    "DdctSum": f("DdctSum", "ORCT", CONFIRMED),
    "NoDocSum": f("NoDocSum", "ORCT", CONFIRMED, "NO document (on-account)"),
    "BoeSum": f("BoeSum", "ORCT", CONFIRMED, "bill of exchange"),
    "U_ORIGIN": f("U_ORIGIN", "ORCT", CANDIDATE),
    "U_SO1_01RETAILONE": f("U_SO1_01RETAILONE", "ORCT", CANDIDATE),
}

# Delivery header / line (§16, §14)
DELIVERY_HEADER: dict[str, Field] = {
    "DocEntry": f("DocEntry", "ODLN", CONFIRMED),
    "DocNum": f("DocNum", "ODLN", CONFIRMED),
    "ObjType": f("ObjType", "ODLN", CONFIRMED),
    "CardCode": f("CardCode", "ODLN", CONFIRMED),
    "SlpCode": f("SlpCode", "ODLN", CONFIRMED),
    "DocDate": f("DocDate", "ODLN", CONFIRMED),
    "DocTotal": f("DocTotal", "ODLN", CONFIRMED),
    "CANCELED": f("CANCELED", "ODLN", CONFIRMED),
    "DocStatus": f("DocStatus", "ODLN", CONFIRMED),
    "UpdateDate": f("UpdateDate", "ODLN", CONFIRMED),
}
DELIVERY_LINE: dict[str, Field] = {
    "DocEntry": f("DocEntry", "DLN1", CONFIRMED),
    "LineNum": f("LineNum", "DLN1", CONFIRMED),
    "ItemCode": f("ItemCode", "DLN1", CONFIRMED),
    "Quantity": f("Quantity", "DLN1", CONFIRMED),
    "WhsCode": f("WhsCode", "DLN1", CONFIRMED),
    "Price": f("Price", "DLN1", CONFIRMED),
    "DiscPrcnt": f("DiscPrcnt", "DLN1", CONFIRMED),
    "GTotal": f("GTotal", "DLN1", CONFIRMED),
    "BaseType": f("BaseType", "DLN1", CONFIRMED),
    "BaseEntry": f("BaseEntry", "DLN1", CONFIRMED),
}

# Inventory movement (§17): confirmed fields from validated inventory_movements_v1_base.sql
INVENTORY_MOVEMENT: dict[str, Field] = {
    "TransNum": f("TransNum", "OINM", CONFIRMED, "SAP journal transaction number"),
    "TransType": f("TransType", "OINM", CONFIRMED, "raw; never replaced by mapping"),
    "BaseRef": f("BASE_REF", "OINM", CONFIRMED, "document link; raw; equals DocNum not DocEntry"),
    "DocLineNum": f("DocLineNum", "OINM", CONFIRMED),
    "ApplObj": f("ApplObj", "OINM", CONFIRMED, "official link: >0 when AppObjAbs valid"),
    "AppObjAbs": f("AppObjAbs", "OINM", CONFIRMED, "official target DocEntry when ApplObj>0"),
    "AppObjLine": f("AppObjLine", "OINM", CONFIRMED, "official target LineNum when ApplObj>0"),
    "Ref1": f("Ref1", "OINM", CONFIRMED),
    "Ref2": f("Ref2", "OINM", CONFIRMED),
    "DocDate": f("DocDate", "OINM", CONFIRMED),
    "ItemCode": f("ItemCode", "OINM", CONFIRMED),
    "InQty": f("InQty", "OINM", CONFIRMED),
    "OutQty": f("OutQty", "OINM", CONFIRMED),
    "TransValue": f("TransValue", "OINM", CONFIRMED),
    "CalcPrice": f("CalcPrice", "OINM", CONFIRMED),
    "Price": f("Price", "OINM", CONFIRMED),
    "Balance": f("Balance", "OINM", CONFIRMED),
    "CardCode": f("CardCode", "OINM", CONFIRMED),
    "SlpCode": f("SlpCode", "OINM", CONFIRMED),
    "Warehouse": f("Warehouse", "OINM", CONFIRMED),
    "UserSign": f("UserSign", "OINM", CONFIRMED),
}

def envelope_build(domain_fields: dict[str, Field]) -> dict[str, tuple[str, str]]:
    """Return logical event envelope for a domain: {event_field: (sap_column, confidence)}."""
    out = {}
    for name, field in domain_fields.items():
        out[name] = (field.name, field.confidence)
    return out