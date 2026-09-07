"""Pure semantic logic: CASH_EVENT construction and stock->document resolution.

Storage-independent, unit-testable without a DB.
Only classifies from CONFIRMED / LEGACY_REFERENCED evidence (never invents).
"""
from __future__ import annotations

from modules.telchi.investigation.atomic.semantic.payment import (
    CASH, CHECK, TRANSFER, CARD, MIXED, OTHER, UNKNOWN,
    classify_payment_method, cancellation_state,
)


# ---- SAP-side CASH_EVENT (payment-derived, §17/§18) ---------------------------
def build_cash_event_from_payment(payment_row: dict) -> dict:
    """Build a CASH_EVENT from an ORCT payment row (SAP side).

    payment_row uses PHYSICAL ORCT column names (CashSum, CheckSum, ...).
    The cash event amount is the cash portion; the full payment total is
    preserved. The physical cash register is not explicit in ORCT, so
    cash_register_id stays None (UNKNOWN) until OJDT/JDT1/OACT evidence.
    """
    method = classify_payment_method(payment_row)
    cash_sum = payment_row.get("CashSum", 0) or 0
    cash_event = {
        "source_system": "SAP",
        "source_object_type": "INCOMING_PAYMENT",
        "source_document_id": payment_row.get("DocEntry"),
        "source_document_number": payment_row.get("DocNum"),
        "business_date": payment_row.get("DocDate"),
        "customer_id": payment_row.get("CardCode"),
        "currency": payment_row.get("DocCurr"),
        "amount_document": payment_row.get("DocTotal"),
        "canceled": cancellation_state(payment_row.get("Canceled")),
        "transaction_id": payment_row.get("TransId"),
        # cash-event specific
        "payment_method": method,
        "cash_amount": round(float(cash_sum), 4),
        "cash_register_id": None,  # UNKNOWN: not explicit in ORCT
        "cash_event_kind": (
            "CASH_ONLY" if cash_sum > 0 and method == CASH
            else "CASH_PORTION" if cash_sum > 0 and method == MIXED
            else "NON_CASH_PAYMENT"
        ),
    }
    return cash_event


# ---- Legacy cash type normalization (§18) -------------------------------------
_LEGACY_CASH_TYPE_MAP = {
    "EFECTIVO": CASH,
    "TARJETA": CARD,
    "CHEQUE": CHECK,
    "DEP/TRAN": TRANSFER,
    "DEPOSITO": TRANSFER,
}


def classify_legacy_cash_type(raw) -> str:
    """Normalize legacy CashType (cjtrn 'Efectivo' / cjddc descriptions).

    Observed values 2022-02: Efectivo, TARJETA DEBITO-CRED, Dep/Tran,
    CHEQUE, CHPDBs. Unknown raw values -> UNKNOWN (never invented).
    """
    if raw is None:
        return UNKNOWN
    token = str(raw).strip().upper()
    for key, label in _LEGACY_CASH_TYPE_MAP.items():
        if key in token:
            return label
    if "CHPDB" in token or token.startswith("CHP"):
        return OTHER
    return UNKNOWN


# ---- Stock movement -> document resolution (DOCNUM_RESOLVE, validated) --------
# Previous validation (validation/inventory_movements/line_link_validation.json,
# CORRECTED_LINE_LINK_V2): OINM.BASE_REF is the DOCUMENT NUMBER (DocNum), NOT
# DocEntry. Resolution: BASE_REF -> header.DocNum -> header.DocEntry, then
# DocLineNum -> line.LineNum. ItemCode equality strengthens the match.
# DocNum collides across document families (13/14/15/...) -> TransType guard is
# MANDATORY (docnum_collision_analysis.json: collision_rate=1.0).
INVENTORY_TRANSTYPE_FAMILIES: dict[int, str] = {
    13: "AR_INVOICE",      # OINV / INV1
    14: "AR_CREDIT_NOTE",  # ORIN / RIN1
    15: "DELIVERY",        # ODLN / DLN1
    18: "AP_INVOICE",      # OPCH / PCH1
    19: "PURCHASE_DELIVERY",  # OPDN / PDN1
    59: "PRODUCTION",      # OWOR (ApplObj>0 official link)
    60: "PRODUCTION",
    67: "INVENTORY_TRANSFER",  # OWTR
}


def resolve_stock_document(movement: dict, header: dict | None,
                           line: dict | None = None) -> dict | None:
    """Resolve an OINM movement row to its source document.

    movement: {trans_type, base_ref, doc_line_num, item_id}
    header:   {doc_num, doc_entry, trans_type_family} or None when the
              expected family lookup failed (missing / canceled doc).
    line:     {line_num, item_id} or None when line unresolved.

    Returns DOCUMENT_RELATION-like dict, or None when header unresolved.
    Never upgrades to a direct method when the header is missing.
    """
    tt = movement.get("trans_type")
    if tt not in INVENTORY_TRANSTYPE_FAMILIES:
        return {
            "resolved": False,
            "reason": "UNSUPPORTED_TRANSTYPE",
            "trans_type": tt,
        }
    if header is None:
        return {
            "resolved": False,
            "reason": "HEADER_UNRESOLVED",
            "trans_type": tt,
            "base_ref": movement.get("base_ref"),
        }
    if header.get("trans_type_family") != INVENTORY_TRANSTYPE_FAMILIES[tt]:
        return {
            "resolved": False,
            "reason": "TRANSTYPE_FAMILY_MISMATCH",
            "trans_type": tt,
            "expected_family": INVENTORY_TRANSTYPE_FAMILIES[tt],
            "header_family": header.get("trans_type_family"),
        }
    relation = {
        "resolved": True,
        "relation_type": "GENERATES",
        "from_system": "SAP",
        "from_object_type": INVENTORY_TRANSTYPE_FAMILIES[tt],
        "from_document_id": header.get("doc_entry"),
        "from_line_id": None,
        "to_system": "SAP",
        "to_object_type": "INVENTORY_MOVEMENT",
        "to_document_id": movement.get("trans_num"),
        "to_line_id": None,
        "match_method": "DIRECT_REFERENCE",
        "confidence": 0.5,
        "evidence": "OINM.BASE_REF=DocNum resolved to header.DocEntry",
    }
    if line is not None and line.get("line_num") == movement.get("doc_line_num"):
        relation["from_line_id"] = line["line_num"]
        if line.get("item_id") == movement.get("item_id"):
            relation["confidence"] = 1.0
            relation["evidence"] = (
                "OINM.BASE_REF=DocNum -> header.DocEntry + DocLineNum=LineNum + ItemCode match"
            )
        else:
            relation["confidence"] = 0.8
            relation["evidence"] = (
                "OINM.BASE_REF=DocNum -> header.DocEntry + DocLineNum=LineNum "
                "(ItemCode differs)"
            )
    return relation